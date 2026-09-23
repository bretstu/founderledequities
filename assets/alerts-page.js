/* THE ALERTS PAGE: everything is free (2026-09-23; the paid tier is gone).
   Three cards, one stream: the weekly letter (Resend), the live founder
   alerts (a watch on the reserved name FOUNDERS, confirmed by one click
   from the inbox like any other watch), and a pointer to the watches,
   which live on the company pages and are managed by the links in their
   own emails. No accounts, no sign-in. */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function boot(){
  hit("view","page");
  const q=new URLSearchParams(location.search).get("watch");
  const said={on:"Confirmed. Every founder's move, as it is filed.",expired:"That link expired; ask again here."}[q]||"";
  $("#lbody").innerHTML=`<div class="lgrid">
    <div class="lcard"><h2>The letter</h2><div class="d">Everything founders did this week, in one email. Sundays.</div>
      <div class="ctl"><form class="lform" onsubmit="return joinLetter(event)"><input type="email" id="lemail" placeholder="you@example.com" required autocomplete="email" aria-label="Your email"><button class="lbtn" type="submit">Send it</button></form></div>
      <div class="fine" id="lfine"></div></div>
    <div class="lcard"><h2>Live founder alerts</h2><div class="d">Every founder&#8217;s open-market buy and discretionary sale, within about ten minutes of the SEC filing.</div>
      <div class="ctl"><form class="lform" onsubmit="return joinLive(event)"><input type="email" id="femail" placeholder="you@example.com" required autocomplete="email" aria-label="Your email"><button class="lbtn" type="submit">Turn on</button></form></div>
      <div class="fine" id="ffine">${esc(said)||"One click from your inbox confirms it; one click from any alert stops it."}</div></div>
    <div class="lcard"><h2>Watches</h2><div class="d">Pick any company and get an email when its chief executive&#8217;s stake moves.</div>
      <div class="ctl"><div class="fine"><a href="/companies/">Find a company &rarr;</a> The field is on every company page; the links in each email manage it.</div></div></div>
  </div>`;
}
async function joinLetter(ev){
  ev.preventDefault();
  const email=($("#lemail").value||"").trim(),f=$("#lfine");
  if(!email)return false;
  try{const q=await fetch("/api/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});const j=await q.json();f.textContent=j.message||"";if(j.ok)$("#lemail").disabled=true;}
  catch(e){f.textContent="Something went wrong; write to hello@founderledequities.com.";}
  return false;
}
async function joinLive(ev){
  ev.preventDefault();
  const email=($("#femail").value||"").trim(),f=$("#ffine");
  if(!email)return false;
  try{const q=await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tk:"FOUNDERS",ceo:"every founder",email})});const j=await q.json();f.textContent=j.message||"";if(j.ok&&!j.watching)$("#femail").disabled=true;}
  catch(e){f.textContent="Something went wrong; write to hello@founderledequities.com.";}
  return false;
}
boot();
