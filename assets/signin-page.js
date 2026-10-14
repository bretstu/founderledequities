/* THE SIGN-IN PAGE (2026-10-14): the address, then the code; on the right
   code this browser holds the reader's token (WATCHES, shared) and the
   nav reads "Your watches" everywhere. A browser already signed in is
   told so, with the way out. */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let EMAIL="";
function boot(){
  hit("view","page");
  if(WATCHES.token){
    /* already signed in: the worker confirms it (a token stopped elsewhere is cleared), then the page says so */
    WATCHES.refresh().then(ws=>{
      if(ws===null||!WATCHES.token)return;
      $("#step1").hidden=true;
      $("#said").innerHTML=`Signed in as <b>${esc(WATCHES.email||"this address")}</b>. <a href="/alerts/">Your watches &rarr;</a> &middot; <a href="#" onclick="return signOut()">Sign out</a>`;
    });
  }
  const next=new URLSearchParams(location.search).get("next");
  if(next&&/^\/[a-z0-9/_\-.]*$/i.test(next))sessionStorage.setItem("fle_next",next);
}
function signOut(){WATCHES.forget();hit("click","signin","out");location.reload();return false;}
async function askCode(ev){
  ev.preventDefault();
  const email=($("#iemail").value||"").trim().toLowerCase(),f=$("#efine"),btn=$("#emailform button");
  if(!email||(btn&&btn.disabled))return false;
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{
    const q=await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({signin:email})});
    const j=await q.json();
    if(!j.ok){f.textContent=j.message||"That didn't work.";if(btn){btn.disabled=false;btn.innerHTML="Send the code &rarr;";}return false;}
    EMAIL=email;hit("click","signin","code-sent");
    $("#iemail").disabled=true;if(btn)btn.textContent="Sent";
    f.innerHTML=`Sent to <b>${esc(email)}</b>. <a href="#" onclick="return again()">Wrong address?</a>`;
    $("#step2").hidden=false;$("#icode").focus();
  }catch(e){f.textContent="Something went wrong; write to hello@founderledequities.com.";if(btn){btn.disabled=false;btn.innerHTML="Send the code &rarr;";}}
  return false;
}
function again(){EMAIL="";$("#iemail").disabled=false;$("#iemail").value="";const b=$("#emailform button");if(b){b.disabled=false;b.innerHTML="Send the code &rarr;";}$("#efine").textContent="";$("#step2").hidden=true;$("#iemail").focus();return false;}
async function checkCode(ev){
  ev.preventDefault();
  const code=($("#icode").value||"").replace(/\D/g,""),f=$("#cfine"),btn=$("#codeform button");
  if(code.length!==6){f.textContent="Six digits.";return false;}
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{
    const q=await fetch("/api/watch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({code,email:EMAIL})});
    const j=await q.json();
    if(!j.ok){f.textContent=j.message||"That isn't the code.";if(btn){btn.disabled=false;btn.innerHTML="Sign in &rarr;";}hit("click","signin","code-wrong");return false;}
    WATCHES.remember(j.token,"","",j.email);
    hit("click","signin","in");
    /* where the reader was going, else the list */
    let to="/alerts/";try{const n=sessionStorage.getItem("fle_next");if(n){to=n;sessionStorage.removeItem("fle_next");}}catch(e){}
    location.href=to;
  }catch(e){f.textContent="Something went wrong; write to hello@founderledequities.com.";if(btn){btn.disabled=false;btn.innerHTML="Sign in &rarr;";}}
  return false;
}
boot();
