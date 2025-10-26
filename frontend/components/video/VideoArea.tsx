'use client';

import { useEffect, useRef, useState } from 'react';

interface WebSocketMessage {
  type: string;
  user_id?: string;
  user_name?: string;
  sender_user_id?: string;
  target_user_id?: string;
  signal_type?: 'offer' | 'answer' | 'ice_candidate';
  data?: any;
  participants?: { user_id: string; user_name: string }[];
}

export default function VideoArea() {
  const [roomCode, setRoomCode] = useState('TEST001');
  const [userName, setUserName] = useState('Тестер');
  const [status, setStatus] = useState('Готов к тестированию');
  const [debugInfo, setDebugInfo] = useState('');
  const [isMuted, setIsMuted] = useState(false);
  const [isVideoEnabled, setIsVideoEnabled] = useState(true);

  const localStreamRef = useRef<MediaStream | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const peerConnectionsRef = useRef<Map<string, RTCPeerConnection>>(new Map());
  const remoteStreamsRef = useRef<Map<string, MediaStream>>(new Map());
  const videoContainerRef = useRef<HTMLDivElement | null>(null);
  const userIdRef = useRef<string>('');

  const iceConfig: RTCConfiguration = {
    iceServers: [
      { urls: 'stun:stun.l.google.com:19302' },
      { urls: 'stun:stun1.l.google.com:19302' },
    ],
  };

  const updateDebugInfo = () => {
    setDebugInfo(`
Комната: ${roomCode}
Пользователь: ${userName} (${userIdRef.current})
Peer Connections: ${peerConnectionsRef.current.size}
Удаленные потоки: ${remoteStreamsRef.current.size}
WebSocket: ${socketRef.current ? socketRef.current.readyState : 'Не подключен'}
Локальный поток: ${localStreamRef.current ? 'Есть' : 'Нет'}
    `);
  };

  const addVideoElement = (id: string, stream: MediaStream, name: string, isLocal: boolean) => {
    const container = videoContainerRef.current;
    if (!container) return;

    const existing = document.getElementById(`video-${id}`);
    if (existing?.parentElement) existing.parentElement.remove();

    const wrapper = document.createElement('div');
    wrapper.className = 'video-wrapper';
    if (isLocal) wrapper.style.border = '3px solid #4CAF50';

    const video = document.createElement('video');
    video.id = `video-${id}`;
    video.srcObject = stream;
    video.autoplay = true;
    video.muted = isLocal;
    video.playsInline = true;

    const label = document.createElement('div');
    label.className = 'video-label';
    label.textContent = name;

    wrapper.appendChild(video);
    wrapper.appendChild(label);
    container.appendChild(wrapper);
  };

  const removeVideoElement = (id: string) => {
    const el = document.getElementById(`video-${id}`);
    if (el?.parentElement) el.parentElement.remove();
    remoteStreamsRef.current.delete(id);
  };

  const createPeerConnection = async (targetUserId: string) => {
    const peerConnection = new RTCPeerConnection(iceConfig);

    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((track: MediaStreamTrack) => {
        peerConnection.addTrack(track, localStreamRef.current!);
      });
    }

    peerConnection.ontrack = (event: RTCTrackEvent) => {
      const [remoteStream] = event.streams;
      remoteStreamsRef.current.set(targetUserId, remoteStream);
      addVideoElement(targetUserId, remoteStream, `Участник ${targetUserId.slice(-4)}`, false);
      updateDebugInfo();
    };

    peerConnection.onicecandidate = (event: RTCPeerConnectionIceEvent) => {
      if (event.candidate && socketRef.current) {
        socketRef.current.send(
          JSON.stringify({
            type: 'webrtc_signal',
            signal_type: 'ice_candidate',
            data: event.candidate,
            target_user_id: targetUserId,
            sender_user_id: userIdRef.current,
          })
        );
      }
    };

    peerConnectionsRef.current.set(targetUserId, peerConnection);

    const offer = await peerConnection.createOffer();
    await peerConnection.setLocalDescription(offer);

    socketRef.current?.send(
      JSON.stringify({
        type: 'webrtc_signal',
        signal_type: 'offer',
        data: offer,
        target_user_id: targetUserId,
        sender_user_id: userIdRef.current,
      })
    );
  };

  const handleWebSocketMessage = async (message: WebSocketMessage) => {
    switch (message.type) {
      case 'user_joined': {
        const user_id = message.user_id!;
        if (user_id !== userIdRef.current) createPeerConnection(user_id);
        break;
      }
      case 'user_left': {
        const user_id = message.user_id!;
        removeVideoElement(user_id);
        const pc = peerConnectionsRef.current.get(user_id);
        if (pc) pc.close();
        peerConnectionsRef.current.delete(user_id);
        break;
      }
      case 'webrtc_signal': {
        const sender_user_id = message.sender_user_id!;
        if (sender_user_id === userIdRef.current) return;

        let pc = peerConnectionsRef.current.get(sender_user_id);
        if (!pc) {
          pc = new RTCPeerConnection(iceConfig);
          if (localStreamRef.current) {
            localStreamRef.current.getTracks().forEach((track: MediaStreamTrack) => {
              pc!.addTrack(track, localStreamRef.current!);
            });
          }

          pc.ontrack = (event: RTCTrackEvent) => {
            const [remoteStream] = event.streams;
            remoteStreamsRef.current.set(sender_user_id, remoteStream);
            addVideoElement(sender_user_id, remoteStream, `Участник ${sender_user_id.slice(-4)}`, false);
            updateDebugInfo();
          };

          pc.onicecandidate = (event: RTCPeerConnectionIceEvent) => {
            if (event.candidate && socketRef.current) {
              socketRef.current.send(
                JSON.stringify({
                  type: 'webrtc_signal',
                  signal_type: 'ice_candidate',
                  data: event.candidate,
                  target_user_id: sender_user_id,
                  sender_user_id: userIdRef.current,
                })
              );
            }
          };

          peerConnectionsRef.current.set(sender_user_id, pc);
        }

        if (message.signal_type === 'offer') {
          await pc.setRemoteDescription(new RTCSessionDescription(message.data));
          const answer = await pc.createAnswer();
          await pc.setLocalDescription(answer);
          socketRef.current?.send(
            JSON.stringify({
              type: 'webrtc_signal',
              signal_type: 'answer',
              data: answer,
              target_user_id: sender_user_id,
              sender_user_id: userIdRef.current,
            })
          );
        } else if (message.signal_type === 'answer') {
          await pc.setRemoteDescription(new RTCSessionDescription(message.data));
        } else if (message.signal_type === 'ice_candidate') {
          await pc.addIceCandidate(new RTCIceCandidate(message.data));
        }

        break;
      }
      case 'participants_list': {
        message.participants?.forEach((p) => {
          if (p.user_id !== userIdRef.current) createPeerConnection(p.user_id);
        });
        break;
      }
    }
    updateDebugInfo();
  };

  const joinRoom = async () => {
    try {
      userIdRef.current = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      setStatus('Получение доступа к медиаустройствам...');

      localStreamRef.current = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      addVideoElement(userIdRef.current, localStreamRef.current, `${userName} (Вы)`, true);

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/video/ws/${roomCode}?user_id=${userIdRef.current}`;

      socketRef.current = new WebSocket(wsUrl);

      socketRef.current.onopen = () => {
        setStatus('Подключено к комнате');
        socketRef.current?.send(
          JSON.stringify({ type: 'user_info', user_id: userIdRef.current, user_name: userName })
        );
        socketRef.current?.send(JSON.stringify({ type: 'get_participants' }));
      };

      socketRef.current.onmessage = (event: MessageEvent) => handleWebSocketMessage(JSON.parse(event.data));
      socketRef.current.onclose = () => setStatus('Соединение закрыто');
      socketRef.current.onerror = (event: Event | unknown) => setStatus('Ошибка WebSocket');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Неизвестная ошибка';
      setStatus('Ошибка: ' + message);
      console.error(err);
    }
  };

  const leaveRoom = () => {
    socketRef.current?.close();

    peerConnectionsRef.current.forEach((pc) => pc.close());
    peerConnectionsRef.current.clear();
    remoteStreamsRef.current.clear();

    localStreamRef.current?.getTracks().forEach((track) => track.stop());
    localStreamRef.current = null;

    if (videoContainerRef.current) videoContainerRef.current.innerHTML = '';
    setStatus('Покинули комнату');
    updateDebugInfo();
  };

  const toggleMute = () => {
    const audioTrack = localStreamRef.current?.getAudioTracks()[0];
    if (!audioTrack) return;

    audioTrack.enabled = !audioTrack.enabled;
    setIsMuted(!audioTrack.enabled);
    setStatus(`Микрофон ${!audioTrack.enabled ? 'выключен' : 'включен'}`);
  };

  const toggleVideo = () => {
    const videoTrack = localStreamRef.current?.getVideoTracks()[0];
    if (!videoTrack) return;

    videoTrack.enabled = !videoTrack.enabled;
    setIsVideoEnabled(videoTrack.enabled);
    setStatus(`Камера ${videoTrack.enabled ? 'включена' : 'выключена'}`);
  };

  const toggleScreenShare = () => {
    setStatus('Демонстрация экрана не реализована в тестовой версии');
  };

  useEffect(() => {
    updateDebugInfo();
  }, []);

  return (
    <div className="container">
      <h1>🧪 Тест видеозвонков</h1>

      <div className="status">{status}</div>

      <div>
        <input value={roomCode} onChange={(e) => setRoomCode(e.target.value)} placeholder="Код комнаты" />
        <input value={userName} onChange={(e) => setUserName(e.target.value)} placeholder="Ваше имя" />
        <button className="btn" onClick={joinRoom}>
          Присоединиться
        </button>
        <button className="btn danger" onClick={leaveRoom}>
          Покинуть
        </button>
      </div>

      <div>
        <button className="btn" onClick={toggleMute}>
          🎤 Микрофон
        </button>
        <button className="btn" onClick={toggleVideo}>
          📹 Камера
        </button>
        <button className="btn" onClick={toggleScreenShare}>
          🖥️ Экран
        </button>
      </div>

      <div className="video-container" ref={videoContainerRef}></div>

      <div>
        <h3>Отладочная информация:</h3>
        <pre>{debugInfo}</pre>
      </div>
    </div>
  );
}
