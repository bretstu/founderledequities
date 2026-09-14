/* the watches page: the signed-in reader's list, a stop on each, one stop for all */
const $=s=>document.querySelector(s);
async function boot(){
  let me=null;
  try{const q=await fetch("/api/me",{cache:"no-store"});if(q.ok)me=await q.json();}catch(e){}
  const body=$("#wbody");
  if(!me||!me.email){
    body.innerHTML=`<div class="wsign"><h2>Sign in to see your list.</h2><p>Pro readers sign in with their email, no password. A free watch (one name) is managed from the links in the email it sends.</p><a class="gopro" href="/#signin">Sign in</a> &nbsp; <a href="/pro/" style="font-size:14px">The plan &rarr;</a></div>`;
    return;
  }
  render();
}
async function render(){
  const body=$("#wbody");
  let list=[];
  try{const q=await fetch("/api/watch",{cache:"no-store"});if(q.ok)list=(await q.json()).watches||[];}catch(e){}
  if(!list.length){body.innerHTML=`<div class="wempty">You're not watching anyone. Open any company's page and press Watch under its record.</div><div class="wfoot"><span></span><a href="/companies/">Every company &rarr;</a></div>`;return;}
  body.innerHTML=`<table class="wl"><thead><tr><th>Company</th><th>Who</th><th></th></tr></thead><tbody>${list.map(w=>`<tr><td class="tk"><a href="/company/${w.tk}/">${w.tk}</a></td><td>${w.ceo||""}</td><td class="act"><button onclick="stopOne('${w.tk}')">Stop</button></td></tr>`).join("")}</tbody></table>
    <div class="wfoot"><span>${list.length} name${list.length===1?"":"s"} &middot; <a href="/companies/">add another</a></span><button class="wall" onclick="stopAll()">Stop all</button></div>`;
}
async function stopOne(tk){await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk,remove:true})});render();}
async function stopAll(){if(!confirm("Stop every watch? Any name can be watched again from its page."))return;await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk:"*",remove:true})});render();}
boot();
