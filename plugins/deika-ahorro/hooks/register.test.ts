import { test, expect } from 'claude-code/testing'

test('registra los tres agentes con su modelo', async ($, on) => {
  const registrados: { name: string; model?: string }[] = []
  on('agent.register', ($, e) => {
    registrados.push({ name: e.name, model: e.model })
    return { value: { agent: `deika-ahorro:${e.name}` } }
  })
  on('session.start', ($, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/home/user', surface: null, isInteractive: false })

  expect(registrados).toEqual([
    { name: 'investigador', model: 'haiku' },
    { name: 'redactor', model: 'sonnet' },
    { name: 'mecanico', model: 'haiku' },
  ])
})

test('añade las reglas de delegación al final del system prompt', async ($, on) => {
  on('prompt.compose', () => ({ sections: [{ id: 'intro', text: 'hola', scope: 'shared' }] }))

  const { sections } = await $.prompt.compose({
    model: 'claude-opus-5-5', promptModel: 'claude-opus-5-5', surfaces: [], tools: [], outputStyle: null, traits: [],
  })

  expect(sections.map(s => s.id)).toEqual(['intro', 'deika-ahorro:reglas'])
  expect(sections[1]?.scope).toBe('session')
})

test('Explore sin modelo va con Haiku; el resto no se toca', async ($, on) => {
  const vistos: (string | undefined)[] = []
  on('ui.toast', () => ({ value: undefined }))
  on('tool.call', { tool: 'Agent' }, ($, e) => {
    vistos.push(e.tool === 'Agent' ? e.model : 'otro')
    return { result: 'ok' }
  })

  await $.tool.call({ tool: 'Agent', description: 'buscar', prompt: 'x', subagent_type: 'Explore' })
  await $.tool.call({ tool: 'Agent', description: 'buscar', prompt: 'x', subagent_type: 'Explore', model: 'sonnet' })
  await $.tool.call({ tool: 'Agent', description: 'tarea', prompt: 'x', subagent_type: 'general-purpose' })

  expect(vistos).toEqual(['haiku', 'sonnet', undefined])
})
