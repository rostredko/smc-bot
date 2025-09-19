package tech.evenmore

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.BufferedReader
import java.io.InputStreamReader

class ProcessStreamer(
    private val command: List<String>,
    private val workingDir: String? = null,
    private val onLine: suspend (String) -> Unit,
    private val onExit: suspend (code: Int) -> Unit = {}
) {
    fun start(scope: CoroutineScope) {
        scope.launch(Dispatchers.IO) {
            val pb = ProcessBuilder(command).redirectErrorStream(true)
            if (!workingDir.isNullOrBlank()) pb.directory(java.io.File(workingDir))
            val process = pb.start()

            BufferedReader(InputStreamReader(process.inputStream)).use { reader ->
                while (true) {
                    val line = reader.readLine() ?: break
                    if (line.isNotBlank()) onLine(line)
                }
            }

            val code = process.waitFor()
            onExit(code)
        }
    }
}