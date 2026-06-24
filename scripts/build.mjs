import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const isWindows = process.platform === 'win32'

const commands = [
  [
    path.join(root, 'backend', isWindows ? 'mvnw.cmd' : 'mvnw'),
    ['-f', path.join(root, 'backend', 'pom.xml'), 'clean', 'package'],
  ],
  [isWindows ? 'npm.cmd' : 'npm', ['--prefix', path.join(root, 'frontend'), 'run', 'build']],
]

for (const [command, args] of commands) {
  const result = spawnSync(command, args, {
    cwd: root,
    shell: isWindows,
    stdio: 'inherit',
  })
  if (result.status !== 0) process.exit(result.status ?? 1)
}

