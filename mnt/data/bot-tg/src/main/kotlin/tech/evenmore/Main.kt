package tech.evenmore

import dev.inmo.tgbotapi.bot.ktor.telegramBot
import dev.inmo.tgbotapi.extensions.api.send.reply
import dev.inmo.tgbotapi.extensions.api.send.sendTextMessage
import dev.inmo.tgbotapi.extensions.behaviour_builder.buildBehaviourWithLongPolling
import dev.inmo.tgbotapi.extensions.behaviour_builder.triggers_handling.onCommand
import dev.inmo.tgbotapi.extensions.utils.extensions.raw.from
import dev.inmo.tgbotapi.types.IdChatIdentifier
import dev.inmo.tgbotapi.types.message.abstracts.CommonMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.runBlocking
import java.io.File
import java.nio.file.Paths
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.ConcurrentHashMap

fun main() = runBlocking {
    val token = Config.resolveBotToken()
    val allowed = Config.resolveAllowedUsers()
    val runner = Config.runner()
    val singleCmd = runner.scripts.first()
    val bot = telegramBot(token)
    val subscribers = ConcurrentHashMap.newKeySet<IdChatIdentifier>()
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    var started = false

    fun CommonMessage<*>.isAllowed(): Boolean {
        if (allowed.isEmpty()) return true
        val uid = from?.id?.chatId?.long ?: return false
        return uid in allowed
    }

    fun resolvedCwd(): File? =
        runner.workingDir?.let { Paths.get(it).toAbsolutePath().normalize().toFile() }

    suspend fun announce(text: String) {
        val now = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"))
        val consoleLine = "[$now] $text"

        println(consoleLine)

        if (subscribers.isNotEmpty()) {
            subscribers.forEach { chat -> bot.sendTextMessage(chat, text) }
        }
    }

    fun runOnce() {
        if (started) return
        started = true

        val cwd = resolvedCwd()
        val cwdStr = cwd?.absolutePath ?: File(".").absolutePath
        println("bot-tg: resolved workingDir = $cwdStr")
        println("bot-tg: starting SINGLE cmd: $singleCmd (cwd=$cwdStr)")

        ProcessStreamer(
            command = singleCmd,
            workingDir = runner.workingDir,
            onLine = { line -> announce(line) },
            onExit = { code ->
                val msg = "⏹ Finished ($code): ${singleCmd.joinToString(" ")}"
                announce(msg)
                started = false
            }
        ).start(scope)
    }

    bot.buildBehaviourWithLongPolling(
        scope = this,
        timeoutSeconds = 30,
        autoDisableWebhooks = true,
        autoSkipTimeoutExceptions = true
    ) {
        onCommand("start") {
            if (!it.isAllowed()) {
                reply(it, "⛔ Not allowed")
                return@onCommand
            }
            val added = subscribers.add(it.chat.id)
            if (added) reply(it, "✅ Subscribed. Launching…") else reply(it, "ℹ️ Already subscribed. Launching…")
            runOnce()
        }

        onCommand("status") {
            val cwdStr = resolvedCwd()?.absolutePath ?: File(".").absolutePath
            reply(it, "🩺 bot-tg up.\nCWD: $cwdStr\nCmd: ${singleCmd.joinToString(" ")}\nRunning: $started")
        }

        onCommand("restart") {
            if (!it.isAllowed()) {
                reply(it, "⛔ Not allowed")
                return@onCommand
            }
            started = false
            reply(it, "♻️ Restarting…")
            runOnce()
        }
    }.join()
}