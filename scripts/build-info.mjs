import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
const snapshot=JSON.parse(fs.readFileSync('public/data/papers.json','utf8'));
fs.writeFileSync('dist/build-info.json',JSON.stringify({
  commit:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),
  workflow_run:process.env.GITHUB_RUN_ID||null,built_at:new Date().toISOString(),
  data_generated_at:snapshot.generated_at,papers:snapshot.coverage.total,
},null,2)+'\n');
