import { copyFileSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'

const from = 'node_modules/@coderline/alphatab/dist/font'
const to = 'public/alphatab/font'
mkdirSync(to, { recursive: true })
for (const name of ['Bravura.woff2', 'Bravura.woff', 'Bravura.otf', 'Bravura.eot', 'Bravura.svg']) {
  copyFileSync(join(from, name), join(to, name))
}
