// Real Chromium regression for Solar Signals calculator. Requires puppeteer-core and Chrome.
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createServer } from 'node:http';
import puppeteer from 'puppeteer-core';
const html = readFileSync(new URL('../index.html', import.meta.url));
const server = createServer((req,res)=>{res.writeHead(200,{'content-type':'text/html'});res.end(html);});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
 const executablePath=[process.env.CHROME_PATH,'/usr/bin/google-chrome','/usr/bin/chromium'].find(p=>p&&existsSync(p));
 assert.ok(executablePath,'Chrome required: no skipped browser pass');
 browser=await puppeteer.launch({executablePath,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 const page=await browser.newPage();
 await page.goto('http://127.0.0.1:'+server.address().port+'/');
 const text=id=>page.$eval('#'+id,e=>e.textContent.trim());
 const edit=(id,value)=>page.$eval('#'+id,(e,v)=>{e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));},String(value));
 const cleared=async label=>{
   assert.match(await text('err'),/Check /,label);
   for(const id of ['up','y1','pb','t25','sdGross','sdNet'])assert.equal(await text(id),'–',label+' '+id);
 };
 assert.notEqual(await text('y1'),'–');
 for(const state of ['AZ','NV','CA']){await page.select('#region',state);assert.notEqual(await text('y1'),'–');}
 await edit('panelKw',0);await cleared('zero panels');
 await edit('panelKw',5.4);assert.equal(await text('err'),'');assert.notEqual(await text('y1'),'–');
 await page.click('#t2');assert.notEqual(await text('sdNet'),'–');
 await edit('taxiCut',150);await cleared('invalid network cut');
 await edit('taxiCut',25);assert.equal(await text('err'),'');
 await page.click('#t3');assert.notEqual(await text('sdNet'),'–');
 await edit('botLife',0);await cleared('zero lifespan');
 await edit('botLife',5);assert.equal(await text('err'),'');assert.notEqual(await text('sdNet'),'–');
 await edit('botLife',0);await page.click('#t1');assert.equal(await text('err'),'');
 await page.select('#grid','off');await edit('genCost',0);await cleared('zero generator price');
 await edit('genCost',0.45);assert.equal(await text('err'),'');
 console.log('Real Chromium calculator regression passed');
} finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
