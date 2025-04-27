let chatSocket;
var selfNick;
let roomName;

const localVideo = document.getElementById('local-video');
const localScreenVideo = document.getElementById('local-screen-video');
const showScreenButton = document.getElementById('toggle-screen-stream-button');
const microButton = document.getElementById('toggle-micro-button');

var peerConnections = {};
var localStream;
var localScreenStream;

document.addEventListener("DOMContentLoaded", async (e) => {
    roomName = JSON.parse(document.getElementById('room-code').textContent);
    localStream = await navigator.mediaDevices.getUserMedia({audio: true, video: false, noiseSuppression: true});
    localVideo.srcObject = localStream;
    
    createWebSocket();

    chatSocket.onopen = () => {
        chatSocket.send(JSON.stringify({type: 'ready'}));
    };

});

showScreenButton.addEventListener('click', async (_) => {
    if (localScreenStream){
        localScreenStream.getTracks().forEach(track => track.stop());
        localScreenStream = undefined;
        
        for (const nick of Object.keys(peerConnections)) {
            hangup(nick, false, false, true)
        }
        chatSocket.send(JSON.stringify({type: 'removeScreen'}));
        toggleScreenVideo();
    } else {
        let data = {members: []};
        Object.keys(peerConnections).forEach(nick => {
            data.members.push({nick: nick})
        });

        if (data.members.length == 0){
            alert('В комнату вы один');
            return;
        }
        localScreenStream = await navigator.mediaDevices.getDisplayMedia({ audio: true, video: true });
        toggleScreenVideo();
        
        chatSocket.send(JSON.stringify({type: 'addScreen'}));
        makeCalls(data, true)

    }
});
microButton.addEventListener('click', (_) => {
    localStream.getAudioTracks()[0].enabled = !localStream.getAudioTracks()[0].enabled;
    muteFlip(microButton);
})

function createPeerConnection(remoteVideo, remoteNick, stream, isScreen, isProvider) {
    let pc = new RTCPeerConnection({
        iceServers: [
            {
                urls: "stun:schepka26.ru:3478"  // Free STUN server
            },
            {
                urls: "turn:schepka26.ru:5349",
                username: "username",
                credential: "password"
            }
        ]
    });
    pc.onicecandidate = e => {
        if (e.candidate) {
            const message = {
                type: 'candidate',
                candidate: e.candidate.candidate,
                sdpMid: e.candidate.sdpMid,
                sdpMLineIndex: e.candidate.sdpMLineIndex,
                isProvider: isProvider,
                isScreen: isScreen,
                to: remoteNick
            };
            
            chatSocket.send(JSON.stringify(message));
        }
    };
    if (isScreen && !isProvider){
        pc.ontrack = e => {
            e.streams[0].getTracks().forEach((track) => {
                stream.addTrack(track);
            });
        };
        
        remoteVideo.srcObject = stream;

        pc.addEventListener('connectionstatechange', () => {
            if (pc.connectionState === 'disconnected' || 
                pc.connectionState === 'failed' ||
                pc.connectionState === 'closed') {
                hangup(remoteNick, false, true, false);
            }
        });

        pc.addTransceiver('video', { direction: 'recvonly' });
        pc.addTransceiver('audio', { direction: 'recvonly' });

    } else {
        pc.ontrack = e => {
            remoteVideo.srcObject = e.streams[0];
        }
        stream.getTracks().forEach(track => pc.addTrack(track, stream));
        remoteVideo.srcObject = stream;
    }

    return pc;
}

function setDataChannelOffer(pc, nick){
    peerConnections[nick]['datachannel'] = pc.createDataChannel('chat');
    setupDataChannelHandlers(nick, peerConnections[nick]['datachannel']);
}

function setDataChannelAnswer(pc, nick){
    pc.ondatachannel = (event) => {
        peerConnections[nick]['datachannel'] = event.channel;
        setupDataChannelHandlers(nick, peerConnections[nick]['datachannel']);
    };
}

function setupDataChannelHandlers(nick, channel) {
    
    channel.onmessage = (event) => {
      console.log('Received:', event.data);
      const data = JSON.parse(event.data)

      switch (data.type) {
        case 'chatMessage':
            newChatMessage(data.sender, data.text, data.time);
            break;
      
        default:
            break;
      }
    };
    
    channel.onclose = () => {
        hangup(nick);
    };
    
    channel.onerror = (error) => {
        hangup(nick);
    };
}

function handleFirstData(data){
    
    selfNick = data.nick;

    return data.members?.length > 1;
}

function makeCalls(data, onlyMyScreen = false) {
    let offersMap = {};
    Promise.all(data.members.map(async member => {

        if (member.nick == selfNick){
            return;
        }

        if (!peerConnections[member.nick]){
            peerConnections[member.nick] = {};
        }
    
        offersMap[member.nick] = {
            sdpVoice: null,
            sdpScreenProvider: null,
            sdpScreenReceiver: null
        }

        //   Если у меня есть экран

        if (localScreenStream){
            const pcsp = createPeerConnection(localScreenVideo, member.nick, localScreenStream, true, true);
            
            const offerProvider = await pcsp.createOffer();
            await pcsp.setLocalDescription(offerProvider);
            
            peerConnections[member.nick]['peerScreenReceiver'] = pcsp;
            offersMap[member.nick].sdpScreenReceiver = offerProvider.sdp;
        }

        if (onlyMyScreen) return;

        //   Если у меня есть голос
        
        const remoteVideo = createNewVideoElement(member.nick);
        const pc = createPeerConnection(remoteVideo, member.nick, localStream, false, false);
        setDataChannelOffer(pc, member.nick);
        
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        
        
        peerConnections[member.nick]['peer'] = pc;
        offersMap[member.nick].sdpVoice = offer.sdp;

        if (member.hasScreen){

            //   Если у друга есть экран

            peerConnections[member.nick]['peerScreenProviderStream'] = new MediaStream();
            const remoteScreenVideo = createNewVideoElement(member.nick, true);
            const pcsr = createPeerConnection(remoteScreenVideo, member.nick, peerConnections[member.nick]['peerScreenProviderStream'], true, false);

            const offerScreen = await pcsr.createOffer();
            await pcsr.setLocalDescription(offerScreen);

            peerConnections[member.nick]['peerScreenProvider'] = pcsr;
            
            offersMap[member.nick].sdpScreenProvider = offerScreen.sdp;
        }
    })).then(() => {
        chatSocket.send(JSON.stringify({type: 'offers', sender: selfNick, data: offersMap}));
    });
}

async function handleOffer(offer, sender) {
    if ((peerConnections[sender]?.peer && !offer.isScreen && !offer.isProvider) ||
            (peerConnections[sender]?.peerScreenProvider && offer.isScreen && offer.isProvider) || 
            (peerConnections[sender]?.peerScreenReceiver && offer.isScreen && !offer.isProvider) ) {
        console.error('existing peerconnection');
        return;
    }

    if (!peerConnections[sender]){
        peerConnections[sender] = {};
    }

    let [isScreen, isProvider] = [offer.isScreen, offer.isProvider];
    delete offer.isScreen;
    delete offer.isProvider;

    let pc
    
    if (isScreen){
        if (isProvider){
            let remoteVideo = createNewVideoElement(sender, true);
            peerConnections[sender]['peerScreenProviderStream'] = new MediaStream();
            pc = createPeerConnection(remoteVideo, sender, peerConnections[sender]['peerScreenProviderStream'], isScreen, !isProvider);
            peerConnections[sender]['peerScreenProvider'] = pc;
        } else {
            pc = createPeerConnection(localScreenVideo, sender, localScreenStream, isScreen, !isProvider);
            peerConnections[sender]['peerScreenReceiver'] = pc;
        }
    } else {
        let remoteVideo = createNewVideoElement(sender);
        pc = createPeerConnection(remoteVideo, sender, localStream, isScreen, false);
        peerConnections[sender]['peer'] = pc;
        setDataChannelAnswer(pc, sender);
    }
    

    await pc.setRemoteDescription(offer);

    const answer = await pc.createAnswer();
    chatSocket.send(JSON.stringify({
        type: 'answer',
        sdp: answer.sdp,
        isProvider: !isProvider,
        isScreen: isScreen,
        to: sender,
        sender: selfNick
    }));
    await pc.setLocalDescription(answer);
}

async function handleAnswer(answer, sender) {
    if ((!peerConnections[sender]?.peer && !answer.isScreen && !answer.isProvider) ||
        (!peerConnections[sender]?.peerScreenProvider && answer.isScreen && answer.isProvider) || 
        (!peerConnections[sender]?.peerScreenReceiver && answer.isScreen && !answer.isProvider) ) {
        console.error('no peerconnection');
        return;
    }
    let [isScreen, isProvider] = [answer.isScreen, answer.isProvider];
    delete answer.isScreen;
    delete answer.isProvider;
    await peerConnections[sender][isScreen ? (isProvider ? 'peerScreenProvider' : 'peerScreenReceiver') : 'peer'].setRemoteDescription(answer);
}

async function handleCandidate(candidate, sender) {
    if ((!peerConnections[sender]?.peer && !candidate.isScreen && !candidate.isProvider) ||
            (!peerConnections[sender]?.peerScreenProvider && candidate.isScreen && candidate.isProvider) || 
            (!peerConnections[sender]?.peerScreenReceiver && candidate.isScreen && !candidate.isProvider) ) {
        console.error('no peerconnection');
        return;
    }
    if (!candidate.candidate) {
        await peerConnections[sender].peer.addIceCandidate(null);
    } else {
        let [isScreen, isProvider] = [candidate.isScreen, candidate.isProvider];
        delete candidate.isScreen;
        delete candidate.isProvider;

        if (isScreen){
            if (isProvider){
                await peerConnections[sender].peerScreenProvider.addIceCandidate(candidate);
            } else {
                await peerConnections[sender].peerScreenReceiver.addIceCandidate(candidate);
            }
        } else {
            await peerConnections[sender].peer.addIceCandidate(candidate);
        }

    }
}

async function hangup(sender, isPeer = true, isProvider = true, isReceiver = true) {

    try {
        if (isPeer){
            peerConnections[sender]?.peer?.close();
            peerConnections[sender]?.datachannel?.close();
            delete peerConnections[sender]?.peer;
            delete peerConnections[sender]?.datachannel;
        }
        if (isReceiver){
            peerConnections[sender]?.peerScreenReceiver?.close();
            delete peerConnections[sender]?.peerScreenReceiver;
        }
        if (isProvider){
            peerConnections[sender]?.peerScreenProvider?.close();
            peerConnections[sender]?.peerScreenProviderStream?.getTracks().forEach(track => track.stop());
            delete peerConnections[sender]?.peerScreenProvider;
            delete peerConnections[sender]?.peerScreenProviderStream;
            removeVideo(sender, true);
        }
        
        
    } catch (error) {
        console.error(error);
    } finally {
        if (isPeer && isProvider && isReceiver || peerConnections[sender] && Object.keys(peerConnections[sender]).length == 0){
            delete peerConnections[sender];
            removeVideo(sender);
        }
        
    }


};

async function reconnetIfNeed(_) {
    if (WebSocket.CLOSED === chatSocket.readyState){
        try {
            console.log('Try reconnect');
            createWebSocket();
            chatSocket.onopen = () => {
                chatSocket.send(JSON.stringify({type: 'reconnect', sender: selfNick, hasScreen: localScreenStream != undefined}));
            };
        } catch {
            console.log('Failed connect');
        }

        setTimeout(reconnetIfNeed, 10000);
    }
}

function createWebSocket(){
    if (location.protocol == 'https:'){
        chatSocket = new WebSocket(
            'wss://'
            + window.location.host
            + '/ws/voice/'
            + roomName
            + '/'
        );
    } else {
        chatSocket = new WebSocket(
            'ws://'
            + window.location.host
            + '/ws/voice/'
            + roomName
            + '/'
        );
    }

    chatSocket.onmessage = (e) => {
        const data = JSON.parse(e.data)
        console.log(data);
        if (!localStream) {
            console.log('not ready yet');
            return;
        }

        let sender = data.sender;
        delete data.sender;
        delete data.to;

        switch (data.type) {
            case 'offer':
                handleOffer(data, sender);
                break;
            case 'answer':
                handleAnswer(data, sender);
                break;
            case 'candidate':
                handleCandidate(data, sender);
                break;
            case 'ready':
                if (!handleFirstData(data)) {
                    console.log('already in call, ignoring');
                    return;
                }
                makeCalls(data);
                break;
            case 'reconnect':
                if (isExist(sender)) {
                    return;
                }
                makeCalls({members: [sender, ]});
                break;
            case 'bye':
                break;
            default:
                console.log('unhandled', e);
                break;
        }
    };

    chatSocket.onclose = reconnetIfNeed;
}

function sendChatMessage(text, time){
    Object.keys(peerConnections).forEach(nick => {
        peerConnections[nick]?.datachannel.send(
            JSON.stringify({
                type: "chatMessage",
                sender: selfNick,
                to: nick,
                text: text,
                time: time
            })
        );
    });
}