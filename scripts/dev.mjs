import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isWindows = process.platform === 'win32'

const processes = [
  spawn(
    path.join(root, 'backend', isWindows ? 'mvnw.cmd' : 'mvnw'),
    ['-f', path.join(root, 'backend', 'pom.xml'), 'spring-boot:run'],
    { cwd: root, shell: isWindows, stdio: 'inherit' },
  ),
  spawn(
    isWindows ? 'npm.cmd' : 'npm',
    ['--prefix', path.join(root, 'frontend'), 'run', 'dev'],
    { cwd: root, shell: isWindows, stdio: 'inherit' },
  ),
]

let stopping = false
function stopAll(exitCode = 0) {
  if (stopping) return
  stopping = true
  for (const child of processes) {
    if (!child.killed) child.kill()
  }
  setTimeout(() => process.exit(exitCode), 300)
}

for (const child of processes) {
  child.on('exit', (code) => {
    if (!stopping && code !== 0) stopAll(code ?? 1)
  })
}

process.on('SIGINT', () => stopAll())
process.on('SIGTERM', () => stopAll())

