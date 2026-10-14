/* THE ALERTS PAGE (rebuilt 2026-09-29; two ways, 2026-10-14): the founder
   stream and a single company, as two panels of one shape; the reader's
   own watches; the sample of what arrives.

   THE EMAIL IS THE ACCOUNT (2026-10-14). A signed-out browser is offered
   the email field: the form posts /api/subscribe, the confirm click writes
   a confirmed FOUNDERS watch and signs the browser in. A signed-in browser
   (WATCHES, shared: the reader's token, earned from the inbox) sees a
   one-click button instead, its list with a stop beside each watch, who it
   is, and Sign out. Per-company watches live on the company pages; the
   search on this page is the way there. */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let SENT=false;   /* a founder watch asked for this visit by a signed-out browser, waiting on the confirm click */
let FORM0="";     /* the founder panel's form as the page shipped it, restored when no state applies */
function boot(){
  const q=new URLSearchParams(location.search);
  /* THE LANDINGS: a FOUNDERS watch confirmed (?watch=on&t=<token>), a stop
     from an email (?watch=off|alloff), an expired confirm link, or the
     "Your watches" link from any alert (?t=<token>). The token signs this
     browser in and the address is cleaned, so a reload or a shared link
     carries neither the token nor a second count. */
  const w=q.get("watch")||"",t=q.get("t")||"";
  const said={on:"Confirmed. The next founder move of 1% or more lands in your inbox, minutes after the filing.",off:"Stopped. No more emails from the founder stream.",alloff:"Stopped. No more emails about anyone.",expired:"That link expired; enter your address again below."}[w]||"";
  $("#said").textContent=said;
  if(w==="on"){hit("click","watch-confirmed","FOUNDERS");WATCHES.remember(t,"FOUNDERS","every founder");}
  else if(w==="off")WATCHES.forget("FOUNDERS");
  else if(w==="alloff")WATCHES.forget();
  else if(t)WATCHES.remember(t);
  if(w||t)history.replaceState(null,"",location.pathname);
  hit("view","page");   /* after the cleaning: the token is a secret and the beacon records the path */
  drawBand();
  drawList();
}
/* THE FOUNDER PANEL: the email field for a stranger; the field kept and the
   button greyed once a confirmation is on its way; one click and no field
   for a signed-in browser; a "Watching" pill for one that holds the founder
   watch. */
function drawBand(){
  const form=$("#subform"),fine=$("#sfine");
  if(!form)return;
  if(!FORM0)FORM0=form.innerHTML;
  if(WATCHES.has("FOUNDERS")){
    form.innerHTML=`<button type="button" class="won" disabled>&#10003; Watching the founders</button>`;
    if(fine)fine.textContent="";
  }else if(WATCHES.token){
    form.innerHTML=`<button type="button" onclick="return joinSigned()">Watch the founders &rarr;</button>`;
    if(fine)fine.textContent="";
  }else if(SENT){
    const inp=form.querySelector("input"),btn=form.querySelector("button");
    if(inp)inp.disabled=true;
    if(btn){btn.disabled=true;btn.textContent="Sent";}
    if(fine)fine.innerHTML=`<b>Check your inbox</b>, or Promotions: one click confirms it.`;
  }else{
    form.innerHTML=FORM0;
    if(fine)fine.textContent="";
  }
}
async function joinAll(ev){
  ev.preventDefault();
  const email=($("#semail").value||"").trim(),f=$("#sfine"),btn=$("#subform button");
  if(!email||(btn&&btn.disabled))return false;
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{const q=await fetch("/api/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});const j=await q.json();hit("click","watch",`FOUNDERS:${j.ok?"sent":"fail"}`);
    if(j.ok){SENT=true;drawBand();}else{f.textContent=j.message||"That didn't work.";if(btn){btn.disabled=false;btn.innerHTML="Watch the founders &rarr;";}}}
  catch(e){hit("click","watch","FOUNDERS:error");f.textContent="Something went wrong; write to hello@founderledequities.com.";if(btn){btn.disabled=false;btn.innerHTML="Watch the founders &rarr;";}}
  return false;
}
/* signed in: the founder watch is one click, on at once */
async function joinSigned(){
  const btn=$("#subform button"),f=$("#sfine");
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{
    const q=await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk:"FOUNDERS",ceo:"every founder",t:WATCHES.token})});
    const j=await q.json();
    if(j.ok&&j.watching){hit("click","watch","FOUNDERS:on");WATCHES.remember(WATCHES.token,"FOUNDERS","every founder");$("#said").textContent="You're watching the founders.";drawBand();drawList();}
    else if(j.signedout){WATCHES.forget();location.href="/signin/?next=/alerts/";}
    else{hit("click","watch","FOUNDERS:fail");if(f)f.textContent=j.message||"That didn't work.";drawBand();}
  }catch(e){hit("click","watch","FOUNDERS:error");if(f)f.textContent="Something went wrong; write to hello@founderledequities.com.";drawBand();}
  return false;
}
/* THE LIST: the worker's answer for the token this browser holds, a stop
   beside each watch and one for everything, who you are and the way out;
   signed out, one line to the sign-in page. */
async function drawList(){
  const mine=$("#mine"),already=$("#already"),body=$("#lbody"),foot=$("#lfoot");
  if(!WATCHES.token){mine.hidden=true;already.hidden=false;return;}
  const ws=await WATCHES.refresh();
  if(ws===null){mine.hidden=true;already.hidden=true;return;}   /* the fetch failed: nothing is claimed either way */
  if(!WATCHES.token){mine.hidden=true;already.hidden=false;drawBand();return;}   /* the token is gone: signed out elsewhere */
  const name=w=>w.tk==="FOUNDERS"?"Every founder":`<span class="tk">${esc(w.tk)}</span>${esc(w.ceo||"")}`;
  const day=d=>{const t=Date.parse(d+"T00:00:00Z");return isNaN(t)?d:new Date(t).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric",timeZone:"UTC"});};
  body.innerHTML=ws.length?ws.map(w=>`<div class="row"><span>${name(w)}${w.since?`<span class="when">since ${esc(day(w.since))}</span>`:""}</span><button class="stop" onclick="return stopOne('${esc(w.token)}','${esc(w.tk)}')">Stop</button></div>`).join("")
    :`<div class="row"><span>Nothing yet. Watch the founders above, or find a company.</span></div>`;
  foot.innerHTML=`Signed in as <b>${esc(WATCHES.email||"this address")}</b> &middot; ${ws.length?`<button type="button" onclick="return stopAll()">Stop everything</button> &middot; `:""}<a href="#" onclick="return signOut()">Sign out</a>`;
  mine.hidden=false;already.hidden=true;
  drawBand();
}
async function stopOne(token,tk){
  try{await fetch(`/api/watch?stop=${token}&json=1`);hit("click","watch",`${tk}:stop`);}catch(e){}
  WATCHES.forget(tk);
  $("#said").textContent=tk==="FOUNDERS"?"Stopped. No more emails from the founder stream.":`Stopped. No more emails about ${tk}.`;
  drawList();
  return false;
}
async function stopAll(){
  try{await fetch(`/api/watch?stopall=${WATCHES.token}&json=1`);hit("click","watch","ALL:stop");}catch(e){}
  $("#said").textContent="Stopped. No more emails about anyone.";
  drawList();   /* signed in still, with nothing watched */
  return false;
}
/* the way out: the browser forgets the token; the nav reads Sign in again */
function signOut(){WATCHES.forget();SENT=false;hit("click","signin","out");location.reload();return false;}
boot();
