import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isWindows = process.platform === 'win32'
const backendPort = Number(process.env.SERVER_PORT ?? 8081)
const resolvedBackendPort = Number.isFinite(backendPort) ? backendPort : 8081
const healthUrl = `http://127.0.0.1:${resolvedBackendPort}/actuator/health`

const processes = []
let stopping = false

function resolvePythonCommand() {
  const candidates = [
    process.env.APP_ALGORITHM_PYTHON_COMMAND,
    process.env.PYTHON_EXECUTABLE,
    ...(['Python313', 'Python312', 'Python311', 'Python310', 'Python39'].map(version => (
      process.env.LOCALAPPDATA
        ? path.join(process.env.LOCALAPPDATA, 'Programs', 'Python', version, 'python.exe')
        : ''
    ))),
    process.env.USERPROFILE
      ? path.join(
        process.env.USERPROFILE,
        '.cache', 'codex-runtimes', 'codex-primary-runtime',
        'dependencies', 'python', 'python.exe',
      )
      : '',
    isWindows ? 'python.exe' : 'python3',
    'python',
  ].filter(Boolean)
  for (const candidate of candidates) {
    const check = spawnSync(candidate, ['-c', 'import numpy'], {
      cwd: root,
      windowsHide: true,
      stdio: 'ignore',
      timeout: 5000,
    })
    if (!check.error && check.status === 0) return candidate
  }
  return isWindows ? 'python.exe' : 'python3'
}

const pythonCommand = resolvePythonCommand()
console.log(`Algorithm Python: ${pythonCommand}`)

const backend = spawn(
  path.join(root, 'backend', isWindows ? 'mvnw.cmd' : 'mvnw'),
  ['-f', path.join(root, 'backend', 'pom.xml'), 'spring-boot:run'],
  {
    cwd: root,
    shell: isWindows,
    stdio: 'inherit',
    env: {
      ...process.env,
      APP_ALGORITHM_PYTHON_COMMAND: pythonCommand,
    },
  },
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
