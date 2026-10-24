import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const python=process.env.APP_PYTHON||path.join(root,'.venv','bin','python');
const api=spawn(python,['-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port','8000','--no-access-log'],{
  cwd:path.join(root,'backend'),stdio:'inherit',env:{...process.env,APP_ENVIRONMENT:'local',APP_DATA_MODE:'fixtures'}});
const web=spawn(process.execPath,[path.join(root,'frontend/node_modules/vite/bin/vite.js'),'--host','0.0.0.0',...process.argv.slice(2)],{
  cwd:path.join(root,'frontend'),stdio:'inherit',env:process.env});
let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;api.kill('SIGTERM');web.kill('SIGTERM');setTimeout(()=>process.exit(code),1000).unref();}
for(const child of [api,web]){child.on('error',error=>{console.error(error.message);stop(1);});child.on('exit',code=>stop(code||0));}
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
