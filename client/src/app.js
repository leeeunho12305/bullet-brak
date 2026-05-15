const statusButton = document.getElementById('statusButton');
const statusOutput = document.getElementById('statusOutput');

statusButton.addEventListener('click', async () => {
  try {
    const response = await fetch('/api/status');
    const data = await response.json();
    statusOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    statusOutput.textContent = `서버 연결 실패: ${error.message}`;
  }
});
