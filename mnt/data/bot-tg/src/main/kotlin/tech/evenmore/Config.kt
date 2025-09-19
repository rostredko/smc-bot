package tech.evenmore

import com.fasterxml.jackson.annotation.JsonIgnoreProperties
import com.fasterxml.jackson.databind.DeserializationFeature
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory
import com.fasterxml.jackson.module.kotlin.registerKotlinModule
import java.io.InputStream

@JsonIgnoreProperties(ignoreUnknown = true)
data class TelegramCfg(
    val token: String? = null,
    val allowedUserIds: String? = null
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class RunnerCfg(
    val workingDir: String? = null,
    val scripts: List<List<String>> = emptyList()
)

@JsonIgnoreProperties(ignoreUnknown = true)
data class AppCfg(
    val app: Inner = Inner()
) {
    @JsonIgnoreProperties(ignoreUnknown = true)
    data class Inner(
        val telegram: TelegramCfg = TelegramCfg(),
        val runner: RunnerCfg = RunnerCfg()
    )
}

object Config {
    private val mapper = ObjectMapper(YAMLFactory())
        .registerKotlinModule()
        .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)

    val loaded: AppCfg by lazy {
        val isr: InputStream = Config::class.java.classLoader
            .getResourceAsStream("application.yml")
            ?: error("application.yml not found in resources")
        mapper.readValue(isr, AppCfg::class.java)
    }

    fun resolveBotToken(): String {
        val env = System.getenv("TELEGRAM_BOT_TOKEN")?.trim().orEmpty()
        val yml = loaded.app.telegram.token?.trim().orEmpty()
        val token = if (env.isNotEmpty()) env else yml
        require(token.isNotEmpty()) {
            "Telegram token is not set. Provide TELEGRAM_BOT_TOKEN env or app.telegram.token in application.yml"
        }
        return token
    }

    fun resolveAllowedUsers(): Set<Long> {
        val fromEnv = System.getenv("ALLOWED_USER_IDS")?.trim().orEmpty()
        val fromYml = loaded.app.telegram.allowedUserIds?.trim().orEmpty()
        val raw = if (fromEnv.isNotEmpty()) fromEnv else fromYml
        if (raw.isEmpty()) return emptySet()
        return raw.split(",")
            .mapNotNull { it.trim().takeIf { s -> s.isNotEmpty() }?.toLongOrNull() }
            .toSet()
    }

    fun runner(): RunnerCfg = loaded.app.runner
}