(function(){
  'use strict';
  const $=id=>document.getElementById(id);
  const vid=$('camera-feed'),cvs=$('capture-canvas'),ctx=cvs?cvs.getContext('2d'):null;
  const btnStart=$('btn-start'),btnStop=$('btn-stop'),cstart=$('cstart');
  const spill=$('spill'),pdot=$('pdot'),ptxt=$('ptxt');
  const aov=$('aov');
  const stimer=$('stimer'),sclock=$('sclock');
  const acnt=$('acnt'),alog=$('alog');
  const ev=$('ev'),eb=$('eb'),el=$('el'),er=$('er');
  const mv=$('mv'),mb=$('mb');

  let stream=null,sessionId=null,detecting=false,loopId=null;
  let t0=null,tint=null,alertCount=0,wasDrowsy=false;

  function beep(){
    try{
      const ac=new(window.AudioContext||window.webkitAudioContext)();
      const o=ac.createOscillator(),g=ac.createGain();
      o.connect(g);g.connect(ac.destination);
      o.type='sine';
      o.frequency.setValueAtTime(660,ac.currentTime);
      o.frequency.exponentialRampToValueAtTime(880,ac.currentTime+.2);
      o.frequency.exponentialRampToValueAtTime(440,ac.currentTime+.6);
      g.gain.setValueAtTime(.38,ac.currentTime);
      g.gain.exponentialRampToValueAtTime(.001,ac.currentTime+.75);
      o.start();o.stop(ac.currentTime+.75);
    }catch(e){}
  }

  function elapsed(){return t0?Math.floor((Date.now()-t0)/1000):0}
  const pad=n=>String(n).padStart(2,'0');
  function fmt(s){return`${pad(Math.floor(s/3600))}:${pad(Math.floor((s%3600)/60))}:${pad(s%60)}`}

  function tick(){
    const s=elapsed(),str=fmt(s);
    if(stimer)stimer.textContent=str;
    if(sclock)sclock.textContent=str;
  }

  function setStatus(state){
    const m={
      'ALERT'  :{cls:'sp-ok',   blink:false},
      'DROWSY' :{cls:'sp-drowsy',blink:true},
      'YAWNING':{cls:'sp-yawn', blink:true},
      'NO FACE':{cls:'sp-nf',   blink:false},
    };
    const s=m[state]||m['NO FACE'];
    if(spill)spill.className='s-pill '+s.cls;
    if(ptxt)ptxt.textContent=state;
    if(pdot)pdot.classList.toggle('blink',s.blink);
  }

  function eCls(v){return v>=.27?'g':v>=.20?'w':'d'}
  function mCls(v){return v<.50?'g':v<.65?'w':'d'}

  function upMetrics(d){
    const e=d.ear||0,m=d.mar||0;
    if(ev){ev.textContent=e.toFixed(3);ev.className='m-val '+eCls(e)}
    if(eb){eb.style.width=Math.min(100,(e/.4)*100)+'%';eb.className='bar-fi '+eCls(e)}
    if(mv){mv.textContent=m.toFixed(3);mv.className='m-val '+mCls(m)}
    if(mb){mb.style.width=Math.min(100,(m/1.2)*100)+'%';mb.className='bar-fi '+mCls(m)}
    if(el)el.textContent=d.ear_left?d.ear_left.toFixed(3):'—';
    if(er)er.textContent=d.ear_right?d.ear_right.toFixed(3):'—';
  }

  function logAlert(type){
    alertCount++;
    if(acnt)acnt.textContent=alertCount;
    if(!alog)return;
    const p=alog.querySelector('p');if(p)p.remove();
    const now=new Date();
    const ts=[now.getHours(),now.getMinutes(),now.getSeconds()].map(pad).join(':');
    const el=document.createElement('div');
    el.className='a-entry';
    el.innerHTML=`<span class="a-ts">${ts}</span>${type==='DROWSY'?'⚠️':'😮'} ${type} detected`;
    alog.insertBefore(el,alog.firstChild);
    if(alog.children.length>20)alog.lastChild.remove();
  }

  function capture(){
    if(!vid||!cvs||!ctx)return null;
    cvs.width=vid.videoWidth||640;cvs.height=vid.videoHeight||480;
    ctx.save();ctx.scale(-1,1);ctx.translate(-cvs.width,0);
    ctx.drawImage(vid,0,0);ctx.restore();
    return cvs.toDataURL('image/jpeg',.72);
  }

  async function detect(){
    if(!detecting)return;
    const img=capture();
    if(img){
      try{
        const res=await fetch('/api/detect',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:img})});
        const d=await res.json();
        if(d.face_detected){
          setStatus(d.status);upMetrics(d);
          if(aov)aov.classList.toggle('on',d.drowsy);
          if(d.drowsy&&!wasDrowsy){beep();logAlert('DROWSY')}
          else if(d.yawning&&!d.drowsy){logAlert('YAWN')}
          wasDrowsy=d.drowsy;
        }else{
          setStatus('NO FACE');upMetrics({ear:0,mar:0,ear_left:0,ear_right:0});
          if(aov)aov.classList.remove('on');wasDrowsy=false;
        }
      }catch(e){}
    }
    loopId=setTimeout(detect,120);
  }

  async function apiStart(){const r=await fetch('/api/session/start',{method:'POST'});const d=await r.json();sessionId=d.session_id}
  async function apiEnd(){
    if(!sessionId)return;
    await fetch('/api/session/end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId,alerts:alertCount,duration:elapsed()})});
    sessionId=null;
  }

  async function startCam(){
    try{
      stream=await navigator.mediaDevices.getUserMedia({video:{width:1280,height:720,facingMode:'user'},audio:false});
      vid.srcObject=stream;await vid.play();
      if(cstart)cstart.style.display='none';
      btnStart.style.display='none';btnStop.style.display='inline-flex';
      if(window._setLive)window._setLive(true);
      alertCount=0;wasDrowsy=false;
      if(acnt)acnt.textContent='0';
      if(alog)alog.innerHTML='<p style="font-size:.76rem;color:var(--t3);text-align:center;padding:14px 0">No alerts this session</p>';
      detecting=true;
      await apiStart();
      t0=Date.now();tint=setInterval(tick,1000);
      detect();
    }catch(e){alert('Camera access denied. Please allow camera permissions and reload.')}
  }

  async function stopCam(){
    detecting=false;clearTimeout(loopId);clearInterval(tint);
    if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}
    vid.srcObject=null;
    if(cstart)cstart.style.display='flex';
    btnStart.style.display='inline-flex';btnStop.style.display='none';
    if(window._setLive)window._setLive(false);
    if(aov)aov.classList.remove('on');
    setStatus('NO FACE');upMetrics({ear:0,mar:0,ear_left:0,ear_right:0});
    await apiEnd();
    ['stimer','sclock'].forEach(id=>{const e=$(id);if(e)e.textContent='00:00:00'});
    t0=null;
  }

  if(btnStart)btnStart.addEventListener('click',startCam);
  if(btnStop)btnStop.addEventListener('click',stopCam);
  setStatus('NO FACE');upMetrics({ear:0,mar:0,ear_left:0,ear_right:0});
})();
