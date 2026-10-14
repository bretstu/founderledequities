/* THE ALERTS PAGE (rebuilt 2026-09-29): one signup, one email. The form
   posts /api/subscribe; the confirm click writes a confirmed FOUNDERS
   watch, which is the whole promise (the weekly letter left the same day).
   Per-company watches live on the company pages; the search on this page
   is the way there. There are no accounts: every alert carries its own
   one-click stop.

   YOUR WATCHES (2026-10-14). The page is also where a reader sees every
   watch their address holds and stops any of them, with no login: the
   token any alert's links carry names the address, /api/watch?mine=<token>
   lists its watches, and a browser that confirmed or made a watch keeps
   the token (WATCHES, shared) so the list is there on the next visit.
   A reader on a new device enters the address and the link is mailed. */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let SENT=false;   /* a founder watch asked for this visit, waiting on the confirm click */
let FORM0="",CAP0="";   /* the band's form and fine print as the page shipped them, restored when no state applies */
function boot(){
  const q=new URLSearchParams(location.search);
  /* THE LANDINGS: a FOUNDERS watch confirmed (?watch=on&t=<token>), a stop
     from an email (?watch=off|alloff), an expired confirm link, or the
     "Your watches" link from any alert (?t=<token>). The token is kept
     and the address cleaned, so a reload or a shared link carries neither
     the token nor a second count. */
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
/* THE BAND: the field for a stranger; the field kept and the button greyed
   once a confirmation is on its way; a "Watching" pill for a browser that
   holds the founder watch. */
function drawBand(){
  const form=$("#subform"),fine=$("#sfine"),cap=$("#lcap .capfine");
  if(!form)return;
  if(!FORM0){FORM0=form.innerHTML;CAP0=cap?cap.innerHTML:"";}
  if(WATCHES.has("FOUNDERS")){
    form.innerHTML=`<button type="button" class="won" disabled>&#10003; Watching the founders</button>`;
    if(fine)fine.textContent="";
    if(cap)cap.innerHTML=`You'll get an email when any founder's stake moves 1% or more. Your watches are below &middot; <a href="#" onclick="return notYou()">not you?</a>`;
  }else if(SENT){
    const inp=form.querySelector("input"),btn=form.querySelector("button");
    if(inp)inp.disabled=true;
    if(btn){btn.disabled=true;btn.textContent="Sent";}
    if(fine)fine.innerHTML=`<b>Check your inbox</b>, or Promotions: one click confirms it.`;
  }else{
    form.innerHTML=FORM0;
    if(fine)fine.textContent="";
    if(cap)cap.innerHTML=CAP0;
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
/* THE LIST: the worker's answer for the token this browser holds, a stop
   beside each watch and one for everything; with no token, the form that
   mails the link instead. */
async function drawList(){
  const mine=$("#mine"),already=$("#already"),body=$("#lbody"),foot=$("#lfoot");
  if(!WATCHES.token){mine.hidden=true;already.hidden=false;return;}
  const ws=await WATCHES.refresh();
  if(ws===null){mine.hidden=true;already.hidden=false;return;}   /* the fetch failed: nothing is claimed */
  if(!ws.length){mine.hidden=true;already.hidden=false;drawBand();return;}   /* the token is gone: stopped elsewhere */
  const name=w=>w.tk==="FOUNDERS"?"Every founder":`<span class="tk">${esc(w.tk)}</span>${esc(w.ceo||"")}`;
  body.innerHTML=ws.map(w=>`<div class="row"><span>${name(w)}${w.since?`<span class="when">since ${esc(w.since)}</span>`:""}</span><button class="stop" onclick="return stopOne('${esc(w.token)}','${esc(w.tk)}')">Stop</button></div>`).join("");
  foot.innerHTML=`<button type="button" onclick="return stopAll('${esc(ws[0].token)}')">Stop everything</button> &middot; <a href="#" onclick="return notYou()">not you?</a>`;
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
async function stopAll(token){
  try{await fetch(`/api/watch?stopall=${token}&json=1`);hit("click","watch","ALL:stop");}catch(e){}
  WATCHES.forget();
  $("#said").textContent="Stopped. No more emails about anyone.";
  SENT=false;
  drawBand();drawList();   /* redrawn from nothing: the forms are back */
  return false;
}
/* a shared machine: the list is someone else's; the browser forgets and the forms come back */
function notYou(){WATCHES.forget();SENT=false;hit("click","watch","notyou");$("#said").textContent="";drawBand();drawList();return false;}
/* the new-device case: the address the alerts go to, and the link is mailed; the reply is the same whatever the address */
async function sendList(ev){
  ev.preventDefault();
  const email=($("#lemail").value||"").trim(),f=$("#lfine"),btn=$("#listform button");
  if(!email||(btn&&btn.disabled))return false;
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{const q=await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({list:email})});const j=await q.json();f.textContent=j.message||"If that address has watches, the list is on its way.";if(btn)btn.textContent="Sent";$("#lemail").disabled=true;hit("click","watch","list:sent");}
  catch(e){f.textContent="Something went wrong; write to hello@founderledequities.com.";if(btn){btn.disabled=false;btn.innerHTML="Send me my watches &rarr;";}}
  return false;
}
boot();
