import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isWindows = process.platform === 'win32'
const backendPort = Number(process.env.SERVER_PORT ?? 8081)
const resolvedBackendPort = Number.isFinite(backendPort) ? backendPort : 8081
const healthUrl = `http://127.0.0.1:${resolvedBackendPort}/actuator/health`

const processes = []
let stopping = false

const backend = spawn(
  path.join(root, 'backend', isWindows ? 'mvnw.cmd' : 'mvnw'),
  ['-f', path.join(root, 'backend', 'pom.xml'), 'spring-boot:run'],
  { cwd: root, shell: isWindows, stdio: 'inherit' },
)
processes.push(backend)

async function waitForBackend(timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs
  while (!stopping && Date.now() < deadline) {
    try {
      const response = await fetch(healthUrl, { signal: AbortSignal.timeout(1500) })
      if (response.ok) return true
    } catch {
      // Spring Boot is still compiling or initializing its database pool.
    }
    await new Promise(resolve => setTimeout(resolve, 500))
  }
  return false
}

async function startFrontendWhenReady() {
  if (!await waitForBackend()) {
    console.error(`Backend did not become healthy within 90 seconds: ${healthUrl}`)
    stopAll(1)
    return
  }
  console.log(`Backend is healthy: ${healthUrl}`)
  const frontend = spawn(
    isWindows ? 'npm.cmd' : 'npm',
    ['--prefix', path.join(root, 'frontend'), 'run', 'dev'],
    {
      cwd: root,
      shell: isWindows,
      stdio: 'inherit',
      env: {
        ...process.env,
        VITE_BACKEND_TARGET: process.env.VITE_BACKEND_TARGET ?? `http://127.0.0.1:${resolvedBackendPort}`,
      },
    },
  )
  processes.push(frontend)
  watchChild(frontend)
}

function stopAll(exitCode = 0) {
  if (stopping) return
  stopping = true
  for (const child of processes) {
    if (!child.killed) child.kill()
  }
  setTimeout(() => process.exit(exitCode), 300)
}

function watchChild(child) {
  child.on('exit', (code) => {
    if (!stopping) stopAll(code ?? 1)
  })
}

watchChild(backend)
void startFrontendWhenReady()

process.on('SIGINT', () => stopAll())
process.on('SIGTERM', () => stopAll())
