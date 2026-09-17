/* THE ALERTS PAGE: three switches on one stream (alerts.html). A signed-in
   reader flips them; a signed-out one is asked for an email for the letter,
   and sent to the plan for the rest. The live founder alert is a watch on
   the reserved name FOUNDERS (functions/api/watch.js), so it shares the
   confirmation, the stop links and the sent-record with every other watch. */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let ME=null,LETTER={on:false},WATCHES=[];
const sw=(id,on,label,fn)=>`<label class="wtog"><input type="checkbox" id="${id}" ${on?"checked":""} onchange="${fn}(this)"><span class="wsw" aria-hidden="true"></span><span class="wlab">${label}</span></label>`;
async function boot(){
  hit("view","page");
  try{const q=await fetch("/api/me",{cache:"no-store"});if(q.ok)ME=await q.json();}catch(e){}
  if(ME&&ME.pro){const b=document.querySelector(".topnav .gopro");if(b){b.textContent="Account";b.setAttribute("href","/account/");}}
  await render();
}
async function render(){
  const signed=!!(ME&&ME.email);
  if(signed){
    try{const q=await fetch("/api/letter",{cache:"no-store"});if(q.ok)LETTER=await q.json();}catch(e){}
    try{const q=await fetch("/api/watch",{cache:"no-store"});if(q.ok)WATCHES=(await q.json()).watches||[];}catch(e){}
  }
  const live=WATCHES.some(w=>w.tk==="FOUNDERS"),names=WATCHES.filter(w=>w.tk!=="FOUNDERS");
  $("#lbody").innerHTML=`<div class="lgrid">
    <div class="lcard"><div class="k">The week</div><h2>The letter</h2><div class="d">Every founder move of the week in one email, Saturday morning. Free.</div>
      ${signed?sw("lsw",LETTER.on,LETTER.on?"Subscribed":"Subscribe","setLetter"):`<form class="lform" onsubmit="return joinLetter(event)"><input type="email" id="lemail" placeholder="you@example.com" required autocomplete="email"><button class="lbtn" type="submit">Send it</button></form>`}
      <div class="fine" id="lfine"></div></div>
    <div class="lcard pro"><div class="k">Every founder &middot; Pro</div><h2>Live founder alerts</h2><div class="d">Every founder&#8217;s move, within about ten minutes of the SEC filing.</div>
      ${ME&&ME.pro?sw("fsw",live,live?"On":"Turn on","setLive")
        :signed?`<a class="lbtn" href="/pro/">Start a 14-day trial</a>`
        :`<div class="lform"><a class="lbtn" href="/pro/">Start a 14-day trial</a><a class="lsign" href="/#signin">Already Pro? Sign in</a></div>`}
      <div class="fine" id="ffine"></div></div>
    <div class="lcard"><div class="k">A name</div><h2>Your watches</h2><div class="d">Any company, founder-led or not, from the switch under its numbers. One is free; a list is Pro.</div>
      ${signed?(names.length?`<div class="wlist"><div class="fine" style="margin-bottom:4px">${names.length} ${names.length===1?"name":"names"}</div>${names.slice(0,4).map(w=>`<div class="row"><span><span class="tk"><a href="/company/${esc(w.tk)}/" style="color:inherit;text-decoration:none">${esc(w.tk)}</a></span>${esc(w.ceo||"")}</span><button class="stop" onclick="stopWatch('${esc(w.tk)}')">stop</button></div>`).join("")}${names.length>4?`<div class="fine" style="margin-top:6px">and ${names.length-4} more &middot; <a href="/account/">Your account &rarr;</a></div>`:""}</div>`:`<div class="fine">You are not watching anyone yet. <a href="/companies/">Find a company &rarr;</a></div>`):`<div class="fine"><a href="/companies/">Find a company &rarr;</a></div>`}
    </div>
  </div>`;
}
async function setLetter(el){
  const on=el.checked;
  try{const q=await fetch("/api/letter",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({on})});const j=await q.json();if(!j.ok){el.checked=!on;$("#lfine").textContent=j.message||"";return;}}
  catch(e){el.checked=!on;$("#lfine").textContent="Something went wrong; write to hello@founderledequities.com.";return;}
  render();
}
async function joinLetter(ev){
  ev.preventDefault();
  const email=($("#lemail").value||"").trim(),f=$("#lfine");
  if(!email)return false;
  try{const q=await fetch("/api/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});const j=await q.json();f.textContent=j.message||"";if(j.ok)$("#lemail").disabled=true;}
  catch(e){f.textContent="Something went wrong; write to hello@founderledequities.com.";}
  return false;
}
async function setLive(el){
  const on=el.checked,f=$("#ffine");
  if(!(ME&&ME.pro)){el.checked=false;f.innerHTML=`Live founder alerts are Pro. <a href="/pro/">The plan &rarr;</a>`;return;}
  try{
    const q=await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(on?{tk:"FOUNDERS",ceo:"every founder"}:{tk:"FOUNDERS",remove:true})});
    const j=await q.json();
    if(!j.ok){el.checked=!on;f.textContent=j.message||"";return;}
  }catch(e){el.checked=!on;f.textContent="Something went wrong; write to hello@founderledequities.com.";return;}
  render();
}
async function stopWatch(tk){await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk,remove:true})});render();}
boot();
