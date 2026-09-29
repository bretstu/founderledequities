/* THE ALERTS PAGE (rebuilt 2026-09-29): one signup, one email. The form
   posts /api/subscribe; the confirm click writes a confirmed FOUNDERS
   watch, which is the whole promise (the weekly letter left the same day).
   Per-company watches live on the company pages; the search on this page
   is the way there. There are no accounts and nothing to manage here:
   every alert carries its own one-click stop. */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function boot(){
  hit("view","page");
  const q=new URLSearchParams(location.search);
  /* the two landings: a FOUNDERS watch confirmed from an old email, or a
     confirm link that expired */
  const said={on:"Confirmed. The next founder move of 1% or more lands in your inbox, minutes after the filing.",expired:"That link expired; enter your address again below."}[q.get("watch")]||"";
  $("#said").textContent=said;
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
