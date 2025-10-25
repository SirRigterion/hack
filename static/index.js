let localStream;
let remoteStream;
let peerConnection;
let socket;

// Конфигурация ICE-серверов (STUN)
const config = {
  iceServers: [
    {
      urls: [
        'stun:stun.l.google.com:19302',
        'stun:stun1.l.google.com:19302'
      ]
    }
  ]
};

// Инициализация медиаустройств
async function initMedia() {
  try {
    // Запрашиваем доступ к камере и микрофону
    localStream = await navigator.mediaDevices.getUserMedia({ 
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { ideal: 30 }
      }, 
      audio: {
        echoCancellation: true,
        noiseSuppression: true
      }
    });
    
    // Отображаем локальный поток
    document.getElementById('local-video').srcObject = localStream;
  } catch (error) {
    console.error('Ошибка доступа к медиаустройствам:', error);
  }
}

// Создание RTCPeerConnection и настройка обработчиков событий
function createPeerConnection() {
  peerConnection = new RTCPeerConnection(config);

  // Отправляем локальные треки удаленной стороне
  localStream.getTracks().forEach(track => {
    peerConnection.addTrack(track, localStream);
  });

  // Обрабатываем поступающие удаленные треки
  peerConnection.ontrack = (event) => {
    remoteStream = event.streams[0];
    document.getElementById('remote-video').srcObject = remoteStream;
  };

  // Собираем и отправляем ICE-кандидаты
  peerConnection.onicecandidate = (event) => {
    if (event.candidate) {
      socket.send(JSON.stringify({
        type: 'ice-candidate',
        candidate: event.candidate
      }));
    }
  };

  // Отслеживаем изменения состояния соединения
  peerConnection.onconnectionstatechange = (event) => {
    console.log('Состояние соединения:', peerConnection.connectionState);
    handleConnectionStateChange(peerConnection.connectionState);
  };
}

// Обработчик изменения состояния соединения
function handleConnectionStateChange(state) {
  const statusElement = document.getElementById('connection-status');
  switch(state) {
    case 'connected':
      statusElement.textContent = 'Соединение установлено';
      statusElement.style.color = 'green';
      break;
    case 'disconnected':
    case 'failed':
      statusElement.textContent = 'Соединение разорвано';
      statusElement.style.color = 'red';
      break;
    case 'connecting':
      statusElement.textContent = 'Установка соединения...';
      statusElement.style.color = 'orange';
      break;
  }
}

// Подключение к WebSocket серверу
function connectWebSocket(roomId) {
  socket = new WebSocket(`ws://localhost:8000/ws/${roomId}`);

  socket.onopen = () => {
    console.log('WebSocket подключен');
    createPeerConnection();
    createOffer();
  };

  socket.onmessage = async (event) => {
    const message = JSON.parse(event.data);
    
    try {
      if (message.type === 'offer') {
        await handleOffer(message.offer);
      } else if (message.type === 'answer') {
        await handleAnswer(message.answer);
      } else if (message.type === 'ice-candidate') {
        await handleNewICECandidate(message.candidate);
      }
    } catch (error) {
      console.error('Ошибка обработки сообщения:', error);
    }
  };
}

// Создание и отправка SDP offer
async function createOffer() {
  try {
    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);
    
    socket.send(JSON.stringify({
      type: 'offer',
      offer: peerConnection.localDescription
    }));
  } catch (error) {
    console.error('Ошибка создания offer:', error);
  }
}

// Обработка входящего SDP offer
async function handleOffer(offer) {
  try {
    if (!peerConnection) {
      createPeerConnection();
    }
    
    await peerConnection.setRemoteDescription(new RTCSessionDescription(offer));
    const answer = await peerConnection.createAnswer();
    await peerConnection.setLocalDescription(answer);
    
    socket.send(JSON.stringify({
      type: 'answer',
      answer: peerConnection.localDescription
    }));
  } catch (error) {
    console.error('Ошибка обработки offer:', error);
  }
}

// Обработка входящего SDP answer
async function handleAnswer(answer) {
  try {
    await peerConnection.setRemoteDescription(new RTCSessionDescription(answer));
  } catch (error) {
    console.error('Ошибка обработки answer:', error);
  }
}

// Обработка нового ICE-кандидата
async function handleNewICECandidate(candidate) {
  try {
    await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
  } catch (error) {
    console.error('Ошибка добавления ICE candidate:', error);
  }
}

// Завершение звонка
function hangUp() {
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }
  
  if (localStream) {
    localStream.getTracks().forEach(track => track.stop());
  }
  
  if (socket) {
    socket.close();
  }
  
  document.getElementById('local-video').srcObject = null;
  document.getElementById('remote-video').srcObject = null;
}

// Инициализация при загрузке страницы
window.onload = async function() {
  await initMedia();
  const urlParams = new URLSearchParams(window.location.search);
  const roomId = urlParams.get('room') || 'default-room';
  connectWebSocket(roomId);
};