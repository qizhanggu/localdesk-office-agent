import fs from 'node:fs/promises';
import { Presentation, PresentationFile } from '@oai/artifact-tool';
const [cardsPath, output, start, end] = process.argv.slice(2);
const cards = JSON.parse(await fs.readFile(cardsPath, 'utf8'));
const deck = Presentation.create({slideSize:{width:1280,height:720}});
const blue='#0B3A82', navy='#082452', cyan='#00A7D9', pale='#F4F8FC', ink='#12233F';
function box(s,x,y,w,h,fill='none',radius='rounded-xl'){const config={geometry:radius==='none'?'rect':'roundRect',position:{left:x,top:y,width:w,height:h},fill,line:{style:'solid',fill:fill==='none'?'none':fill,width:0}};if(radius!=='none')config.borderRadius=radius;return s.shapes.add(config);}
function text(s,t,x,y,w,h,size=24,color=ink,bold=false){const a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{style:'solid',fill:'none',width:0}});a.text=t;a.text.style={fontSize:size,color,bold};return a;}
function chrome(s,n,title){s.background.fill='white';box(s,0,0,1280,18,blue,'none');text(s,'LocalDesk | AI Weekly Briefing',72,36,600,24,16,blue,true);text(s,`${n} / ${cards.length+3}`,1130,36,80,24,14,'#5B6B82');text(s,title,72,82,1100,54,34,ink,true);}
let s=deck.slides.add();s.background.fill=blue;box(s,72,88,8,410,cyan,'none');text(s,'本周AI资讯汇报',110,132,780,70,54,'white',true);text(s,`${start} — ${end}`,114,226,560,38,26,'#CDE7FF');text(s,'大模型 · Agent 产品 · 产业应用',114,292,680,34,24,'#FFFFFF');text(s,'公开来源｜可编辑PPTX｜本地人工确认后交付',114,540,700,28,18,'#CDE7FF');
s=deck.slides.add();chrome(s,2,'本周观察：能力、产品与基础设施同时推进');const take=[['大模型','前沿能力持续向产品与工作流下沉'],['Agent 产品','工具调用、审计与协作成为产品差异点'],['产业应用','算力与治理决定规模化落地速度']];take.forEach((v,i)=>{const y=180+i*135;box(s,92,y,1050,96,pale);text(s,v[0],126,y+22,190,34,24,blue,true);text(s,v[1],350,y+23,730,36,22,ink);});
cards.forEach((c,i)=>{s=deck.slides.add();chrome(s,i+3,['大模型研究','Agent 产品','产业应用'][i]||c.category);box(s,74,156,1130,436,pale);text(s,c.title,112,190,1030,62,29,ink,true);text(s,`发布日期：${c.published}`,112,270,340,26,17,'#5B6B82');text(s,'摘要',112,326,130,28,21,blue,true);text(s,c.summary,112,364,970,68,20,ink);text(s,'价值判断',112,454,170,28,21,blue,true);text(s,c.value,112,492,970,62,20,ink);text(s,c.url,112,616,1010,24,14,'#2563EB');});
s=deck.slides.add();chrome(s,cards.length+3,'来源与人工确认');text(s,'本周来源',92,166,260,35,25,blue,true);cards.forEach((c,i)=>{text(s,`${i+1}. ${c.title}`,100,220+i*76,900,28,19,ink,true);text(s,c.url,100,252+i*76,1000,20,14,'#2563EB');});text(s,'交付前请在 LocalDesk 确认页面核验来源与摘要；邮件草稿不会自动发送。',92,570,1000,30,18,'#5B6B82');
const pptx=await PresentationFile.exportPptx(deck);await pptx.save(output);
