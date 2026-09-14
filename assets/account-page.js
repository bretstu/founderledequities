/* the account page: the letter on or off, the watches, the plan, sign out */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let ME=null;
async function boot(){
  hit("view","page");   /* THE PAGE COUNTS ITS OWN VISITORS, like the home page: the same beacon, shared */
  try{const q=await fetch("/api/me",{cache:"no-store"});if(q.ok)ME=await q.json();}catch(e){}
  const body=$("#abody");
  if(!ME||!ME.email){
    body.innerHTML=`<div class="asign"><h2>Sign in to see your account.</h2><p>Pro readers sign in with their email, no password. If you only read the letter or watch one founder, there is nothing to manage here: the links in each email do it.</p><a class="gopro" href="/#signin">Sign in</a> &nbsp; <a href="/pro/" style="font-size:14px">The plan &rarr;</a></div>`;
    return;
  }
  $("#who").textContent=ME.email;
  const b=document.querySelector(".topnav .gopro");if(b){b.textContent="Account";b.setAttribute("href","/account/");}
  render();
}
async function render(){
  const body=$("#abody");
  let letter={on:false},watches=[];
  try{const q=await fetch("/api/letter",{cache:"no-store"});if(q.ok)letter=await q.json();}catch(e){}
  try{const q=await fetch("/api/watch",{cache:"no-store"});if(q.ok)watches=(await q.json()).watches||[];}catch(e){}
  body.innerHTML=`
    <div class="ablock"><h2>Monday letter</h2>
      <div class="arow"><div class="l"><span>${letter.on?"On":"Off"}</span><span class="mut">${letter.on?"the week's tape, every Monday morning":"you are not on the list"}</span></div>
        <button class="abtn${letter.on?"":" primary"}" onclick="setLetter(${letter.on?"false":"true"})">${letter.on?"Stop":"Join"}</button></div>
    </div>
    <div class="ablock"><h2>Watches</h2>
      ${watches.length?watches.map(w=>`<div class="arow"><div class="l"><span class="tk"><a href="/company/${esc(w.tk)}/" style="color:inherit;text-decoration:none">${esc(w.tk)}</a></span><span>${esc(w.ceo||"")}</span></div><button class="abtn" onclick="stopWatch('${esc(w.tk)}')">Remove</button></div>`).join("")
        :`<div class="anote">You are not watching anyone. Open any company page and press Watch under its numbers.</div>`}
      <div class="anote">An email the morning after any of them buys on the open market or sells at their own discretion. <a href="/companies/">Watch another &rarr;</a>${watches.length>1?` &middot; <a href="#" onclick="stopAll();return false">Stop all</a>`:""}</div>
    </div>
    <div class="ablock"><h2>Pro</h2>
      <div class="arow"><div class="l"><span>${ME.pro?"$15 a month":"Not a subscriber"}</span><span class="mut">${ME.pro?"every company, the archive, the tape at every window, export, a list of watches":"S&P 500 current stakes and the last twelve months are open"}</span></div>
        ${ME.pro?`<a class="abtn" href="/api/portal">Manage billing</a>`:`<a class="abtn primary" href="/pro/">Start trial</a>`}</div>
    </div>
    <div class="aout"><a href="/api/logout">Sign out</a></div>`;
}
async function setLetter(on){await fetch("/api/letter",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({on})});render();}
async function stopWatch(tk){await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk,remove:true})});render();}
async function stopAll(){if(!confirm("Stop every watch? Any name can be watched again from its page."))return;await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk:"*",remove:true})});render();}
boot();
