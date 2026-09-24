/* THE ALERTS PAGE (2026-09-24): one signup, two emails. The form posts
   /api/subscribe; the confirm click puts the address on the Monday letter's
   list AND writes a confirmed FOUNDERS watch, so one signup is the whole
   promise. Per-company watches live on the company pages. There are no
   accounts and nothing here to manage: every alert carries its own
   one-click stop, and the Monday email its own unsubscribe link. */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function boot(){
  hit("view","page");
  const q=new URLSearchParams(location.search);
  /* the two landings: a FOUNDERS watch confirmed from an old email, or a
     confirm link that expired */
  const said={on:"Confirmed. The next founder move of 1% or more lands in your inbox, minutes after the filing.",expired:"That link expired; enter your address again here."}[q.get("watch")]||"";
  $("#lbody").innerHTML=`<div class="lgrid">
    <div class="lcard"><h2>Watch the founders</h2><div class="d">The alert when a founder&#8217;s stake moves 1% or more, within about ten minutes of the SEC filing, and the week in one email every Sunday. One signup covers both.</div>
      <div class="ctl"><form class="lform" onsubmit="return joinAll(event)"><input type="email" id="semail" placeholder="you@example.com" required autocomplete="email" aria-label="Your email"><button class="lbtn" type="submit">Watch the founders &rarr;</button></form></div>
      <div class="fine" id="sfine">${esc(said)||"One click from your inbox confirms it."}</div></div>
    <div class="lcard"><h2>Watch one company</h2><div class="d">An email when that chief executive&#8217;s stake moves: any trade, or any other filing that moves it by 1% or more.</div>
      <div class="ctl"><div class="fine"><a href="/companies/">Find a company &rarr;</a> The field is on every company page; the links in each email manage it.</div></div></div>
  </div>`;
}
async function joinAll(ev){
  ev.preventDefault();
  const email=($("#semail").value||"").trim(),f=$("#sfine");
  if(!email)return false;
  try{const q=await fetch("/api/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});const j=await q.json();f.textContent=j.message||"";if(j.ok)$("#semail").disabled=true;hit("act","subscribe","alerts-page");}
  catch(e){f.textContent="Something went wrong; write to hello@founderledequities.com.";}
  return false;
}
boot();
