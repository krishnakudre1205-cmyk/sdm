// static/app.js
const MODULE_FIELDS = {
  child: [
    {name:'name', label:'Child Name', type:'text'},
    {name:'age', label:'Age (years)', type:'number'},
    {name:'weight', label:'Weight (kg)', type:'number'}
  ],
  household: [
    {name:'household_id', label:'Household ID', type:'text'},
    {name:'members', label:'Number of members', type:'number'}
  ],
  maternal: [
    {name:'mother_name', label:'Mother Name', type:'text'},
    {name:'anc_visit', label:'ANC Visit Count', type:'number'}
  ],
  ncd: [
    {name:'patient_name', label:'Patient Name', type:'text'},
    {name:'bp', label:'BP (sys/dia)', type:'text'},
    {name:'diabetes', label:'Diabetes (yes/no)', type:'text'}
  ],
  reports: [],
  voice_assistant: []
};

function el(q){return document.querySelector(q)}
function els(q){return document.querySelectorAll(q)}

function updateOnlineStatus(){
  const online = navigator.onLine;
  let ind = el('#onlineIndicator');
  ind.textContent = online ? 'Online' : 'Offline';
  ind.style.color = online ? '#198754' : '#dc3545';
  el('#sysStatus').textContent = online ? 'Online - syncing enabled' : 'Offline - using local cache';
  updateQueueCount();
  if(online) {
    syncQueueToServer();
    fetchNotifications();
  }
}

window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
document.addEventListener('DOMContentLoaded', ()=>{
  updateOnlineStatus();
  setupModuleLinks();
  const langSelect = el('#langSelect');
  if(langSelect) {
    langSelect.addEventListener('change', onLangChange);
    onLangChange();
  }
  const syncBtn = el('#syncBtn');
  if(syncBtn) syncBtn.addEventListener('click', syncQueueToServer);
  fetchNotifications();
  setupUserManagementForm();
});

function onLangChange(){
  const sel = el('#langSelect');
  if(!sel) return;
  const lang = sel.value;
  const greetText = {
    en: "Hello! Welcome to ASHA dashboard.",
    hi: "नमस्ते! ASHA डॅशबोर्ड मध्ये आपले स्वागत आहे।",
    mr: "नमस्कार! ASHA डॅशबोर्डमध्ये आपले स्वागत आहे."
  }[lang] || "Hello!";
  const vg = el('#voiceGreeting');
  if(vg) vg.textContent = greetText;
  try {
    const ut = new SpeechSynthesisUtterance(greetText);
    ut.lang = (lang === 'hi' ? 'hi-IN' : (lang==='mr' ? 'mr-IN' : 'en-US'));
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(ut);
  } catch(e){}
}

function setupModuleLinks(){
  els('.module-link').forEach(a=>{
    a.addEventListener('click', (ev)=>{
      ev.preventDefault();
      const module = a.dataset.module;
      renderModule(module);
    });
  });
}

function renderModule(module){
  const template = document.getElementById('module-form-template');
  const clone = template.content.cloneNode(true);
  clone.querySelector('#moduleTitle').textContent = module.replace('_', ' ').toUpperCase();
  const fieldsDiv = clone.querySelector('#moduleFields');
  const fields = MODULE_FIELDS[module] || [];
  if(fields.length === 0){
    fieldsDiv.innerHTML = "<p class='text-muted'>No structured form for this module. Use voice assistant or other options.</p>";
  } else {
    fields.forEach(f=>{
      const wrapper = document.createElement('div');
      wrapper.className = 'mb-2';
      wrapper.innerHTML = `<label class="form-label">${f.label}</label><input name="${f.name}" class="form-control" type="${f.type}" />`;
      fieldsDiv.appendChild(wrapper);
    });
  }

  const area = el('#moduleArea');
  area.innerHTML = '';
  area.appendChild(clone);

  const form = area.querySelector('#moduleForm');
  form.addEventListener('submit', (e)=>{
    e.preventDefault();
    const data = {};
    new FormData(form).forEach((v,k)=>data[k]=v);
    if(navigator.onLine){
      fetch('/api/submit_entry', {
        method:'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({module: module, data: data})
      }).then(r=>r.json()).then(j=>{
        alert('Submitted. Flagged: ' + j.flagged);
        fetchNotifications();
      }).catch(err=>{
        alert('Failed to submit online; saving locally.');
        saveToLocalQueue(module, data);
      });
    } else {
      saveToLocalQueue(module, data);
    }
  });

  const saveLocalBtn = area.querySelector('#saveLocal');
  saveLocalBtn.addEventListener('click', ()=>{
    const data = {};
    new FormData(form).forEach((v,k)=>data[k]=v);
    saveToLocalQueue(module, data);
  });
}

function saveToLocalQueue(module, data){
  const key = 'localQueue_v1';
  const cur = JSON.parse(localStorage.getItem(key) || '[]');
  cur.push({module: module, data: data, ts: Date.now()});
  localStorage.setItem(key, JSON.stringify(cur));
  updateQueueCount();
  alert('Saved locally to queue. It will sync when online.');
}

function updateQueueCount(){
  const key = 'localQueue_v1';
  const cur = JSON.parse(localStorage.getItem(key) || '[]');
  const elq = el('#queueCount');
  if(elq) elq.textContent = cur.length;
}

function syncQueueToServer(){
  const key = 'localQueue_v1';
  const cur = JSON.parse(localStorage.getItem(key) || '[]');
  if(cur.length === 0){
    alert('No pending items to sync.');
    return;
  }
  if(!navigator.onLine){
    alert('You are offline. Connect to internet to sync.');
    return;
  }
  fetch('/api/sync_queue', {
    method:'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({items: cur})
  }).then(r=>r.json()).then(j=>{
    alert(`Synced ${j.synced} items`);
    localStorage.removeItem(key);
    updateQueueCount();
    fetchNotifications();
  }).catch(e=>{
    console.error(e);
    alert('Sync failed');
  });
}

function fetchNotifications(){
  fetch('/api/notifications').then(r=>r.json()).then(data=>{
    const area = el('#notificationsArea');
    if(!area) return;
    if(data.length === 0) area.innerHTML = '<p>No notifications</p>';
    else {
      let html = '<ul class="list-group">';
      data.forEach(n=>{
        html += `<li class="list-group-item d-flex justify-content-between align-items-start">
          <div>${n.message}<div class="text-muted small">to: ${n.target_user} at ${n.created_at}</div></div>
          <div>${n.sent ? '<span class="badge bg-success">Sent</span>' : '<span class="badge bg-warning">Pending</span>'}</div>
        </li>`;
      });
      html += '</ul>';
      area.innerHTML = html;
    }
  });
}

/* User management helper - only used on users.html */
function setupUserManagementForm(){
  const form = document.getElementById('createUserForm');
  if(!form) return;
  form.addEventListener('submit', function(e){
    e.preventDefault();
    const fd = new FormData(this);
    const obj = {};
    fd.forEach((v,k)=>obj[k]=v);
    fetch('/api/create_user', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(obj)
    }).then(r=>r.json()).then(j=>{
      if(j.ok) location.reload();
      else alert(j.message || 'Failed');
    })
  });

  document.querySelectorAll('.del').forEach(btn=>{
    btn.addEventListener('click', ()=> {
      if(!confirm('Delete user?')) return;
      const id = btn.dataset.id;
      fetch('/api/delete_user', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id: id})
      }).then(r=>r.json()).then(j=>{
        if(j.ok) location.reload();
        else alert('Failed');
      })
    })
  });
}
