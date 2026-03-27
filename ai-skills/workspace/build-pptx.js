const pptxgen = require('pptxgenjs');
const html2pptx = require('/Users/polarischen/.claude/plugins/cache/anthropic-agent-skills/example-skills/69c0b1a06741/skills/pptx/scripts/html2pptx');
const path = require('path');

async function build() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';
  pptx.author = 'AI Coding Workshop';
  pptx.title = 'AI Agent Skills 深度解析';

  const slides = [
    'slide01-cover.html',
    'slide02-overview.html',
    'slide03-skill-trigger.html',
    'slide04-skill-chain.html',
    'slide05-subagent-dispatch.html',
    'slide06-review-pipeline.html',
    'slide07-tdd.html',
    'slide08-hooks.html',
    'slide09-voltagent-arch.html',
    'slide10-prompt-patterns.html',
    'slide11-meta-orchestration.html',
    'slide12-install.html',
    'slide13-evolution.html',
    'slide14-summary.html'
  ];

  const dir = '/Users/polarischen/code/ai-coding/ai-skills/workspace';

  for (let i = 0; i < slides.length; i++) {
    const file = path.join(dir, slides[i]);
    console.log(`Processing slide ${i + 1}: ${slides[i]}`);
    try {
      await html2pptx(file, pptx);
    } catch (e) {
      console.error(`Error on ${slides[i]}:`, e.message);
    }
  }

  const outPath = path.join(dir, '..', 'AI-Agent-Skills-Deep-Dive.pptx');
  await pptx.writeFile({ fileName: outPath });
  console.log(`Presentation saved to: ${outPath}`);
}

build().catch(console.error);
