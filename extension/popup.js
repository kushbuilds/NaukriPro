const SERVER_URL = 'http://localhost:8080';

const statusOff = document.getElementById('statusOff');
const statusOn = document.getElementById('statusOn');
const startBtn = document.getElementById('startBtn');
const openBtn = document.getElementById('openBtn');
const stopBtn = document.getElementById('stopBtn');

// Check if server is running
async function checkServer() {
  try {
    const resp = await fetch(SERVER_URL, { method: 'HEAD', signal: AbortSignal.timeout(2000) });
    if (resp.ok) {
      statusOff.classList.add('hidden');
      statusOn.classList.remove('hidden');
      startBtn.classList.add('hidden');
      stopBtn.classList.remove('hidden');
      return true;
    }
  } catch (e) {}
  statusOff.classList.remove('hidden');
  statusOn.classList.add('hidden');
  startBtn.classList.remove('hidden');
  stopBtn.classList.add('hidden');
  return false;
}

// Open the web UI
openBtn.addEventListener('click', () => {
  chrome.tabs.create({ url: SERVER_URL });
});

// Start server (opens terminal)
startBtn.addEventListener('click', () => {
  // Can't start server directly from extension, open instructions
  chrome.tabs.create({ url: SERVER_URL });
  // Show reminder
  statusOff.querySelector('div:last-child') || 
  (statusOff.textContent = '');
  statusOff.innerHTML = '<div class="dot dot-red"></div>Run: python app.py in terminal first';
});

// Stop server
stopBtn.addEventListener('click', async () => {
  try {
    await fetch(SERVER_URL + '/api/stop', { method: 'POST' });
  } catch (e) {}
  checkServer();
});

// Check on popup open
checkServer();
