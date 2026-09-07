const token = document.body.dataset.token;
function track(kind, label, details={}) { fetch(`/api/public/proposals/${token}/activity`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind,label,details}),keepalive:true}).catch(()=>{}); }
track("proposal_opened", "Personal proposal opened");
document.querySelectorAll("[data-package-button]").forEach(button=>button.addEventListener("click",()=>{track("package_viewed",`${button.dataset.packageButton} selected`,{package:button.dataset.packageButton});window.location.href=`mailto:mark@perfectweddingsbymark.uk?subject=${encodeURIComponent(button.dataset.packageButton)}&body=${encodeURIComponent("Hi Mark, we would like to know more about " + button.dataset.packageButton + ".")}`}));
document.querySelectorAll("video").forEach(video=>video.addEventListener("play",()=>track("film_played",`${video.dataset.film||"Highlight film"} played`),{once:true}));
document.querySelector("[data-booking]")?.addEventListener("click",()=>track("booking_clicked","Secure booking area clicked"));
document.querySelector("[data-consultation]")?.addEventListener("click",()=>track("consultation_clicked","Ask Mark a question clicked"));

