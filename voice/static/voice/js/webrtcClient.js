let chatSocket;
let selfNick;
let roomName;

const hangupButton = document.getElementById('hangupButton');
hangupButton.disabled = true;

const localVideo = document.getElementById('localVideo');

var pc1;
var peerConnections = {};
var localStream;

document.addEventListener("DOMContentLoaded", async (e) => {
    roomName = JSON.parse(document.getElementById('room-code').textContent);
    localStream = await navigator.mediaDevices.getUserMedia({audio: true, video: false, noiseSuppression: true});
    localVideo.srcObject = localStream;

    hangupButton.disabled = false;
    
    createWebSocket();

    chatSocket.onopen = () => {
        chatSocket.send(JSON.stringify({type: 'ready'}));
    };

});

hangupButton.onclick = async () => {
    hangup();
    chatSocket.send(JSON.stringify({type: 'bye'}));
};

async function hangup(sender) {
    document.querySelectorAll(`video[nick="${sender}"]`).forEach(videoElement => {
        videoElement.remove();
    });
    try {

        peerConnections[sender].peer.close();

        delete peerConnections[sender];

    } catch (error) {
        console.error(error);
    }

    // TODO
    // if (pc1) {
    //     pc1.close();
    //     pc1 = null;
    // }
    // localStream.getTracks().forEach(track => track.stop());
    // localStream = null;
    // hangupButton.disabled = true;
};

function createPeerConnection(remoteVideo, remoteNick) {
    let pc = new RTCPeerConnection();
    pc.onicecandidate = e => {
        if (e.candidate) {
            const message = {
                type: 'candidate',
                candidate: e.candidate.candidate,
                sdpMid: e.candidate.sdpMid,
                sdpMLineIndex: e.candidate.sdpMLineIndex,
                to: remoteNick
            };
            if (!message.to){
                console.log(remoteNick)
            }
            chatSocket.send(JSON.stringify(message));
        }
    };
    pc.ontrack = e => {
        remoteVideo.srcObject = e.streams[0];
    }
    localStream.getTracks().forEach(track => pc.addTrack(track, localStream));

    return pc;
}

function handleFirstData(data){
    
    selfNick = data.nick;

    return data.members?.length > 1;
}

function makeCalls(data) {
    let offersMap = {};
    Promise.all(data.members.map(async member => {

        if (member == selfNick){
            return;
        }
        
        let remoteVideo = createNewVideoElement(member);
        let pc = createPeerConnection(remoteVideo, member);
        
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        
        peerConnections[member] = {'video': remoteVideo, 'peer': pc};
        offersMap[member] = offer.sdp;
    })).then(() => {
        chatSocket.send(JSON.stringify({type: 'offers', sender: selfNick, data: offersMap}));
    });
    // chatSocket.send(JSON.stringify({type: 'offer', sdp: offer.sdp}));
}

async function handleOffer(offer, sender) {
    if (peerConnections[sender]?.peer) {
        console.error('existing peerconnection');
        return;
    }

    let remoteVideo = createNewVideoElement(sender);
    let pc = createPeerConnection(remoteVideo, sender);

    peerConnections[sender] = {'video': remoteVideo, 'peer': pc};

    await pc.setRemoteDescription(offer);

    const answer = await pc.createAnswer();
    chatSocket.send(JSON.stringify({
        type: 'answer',
        sdp: answer.sdp,
        to: sender,
        sender: selfNick
    }));
    await pc.setLocalDescription(answer);
}

async function handleAnswer(answer, sender) {
    if (!peerConnections[sender]?.peer) {
        console.error('no peerconnection');
        return;
    }
    await peerConnections[sender].peer.setRemoteDescription(answer);
}

async function handleCandidate(candidate, sender) {
    if (!peerConnections[sender]?.peer) {
        console.error('no peerconnection');
        return;
    }
    if (!candidate.candidate) {
        await peerConnections[sender].peer.addIceCandidate(null);
    } else {
        await peerConnections[sender].peer.addIceCandidate(candidate);
    }
}

async function reconnetIfNeed(_) {
    if (WebSocket.CLOSED === chatSocket.readyState){
        try {
            console.log('Try reconnect');
            createWebSocket();
            chatSocket.onopen = () => {
                chatSocket.send(JSON.stringify({type: 'reconnect', sender: selfNick}))
            };
        } catch {
            console.log('Failed connect');
        }

        setTimeout(reconnetIfNeed, 10000);
    }
}

function isExist(nick) {
    return nick == selfNick || document.querySelectorAll(`video[nick="${nick}"]`).length > 0;
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
                hangup(sender);
                break;
            default:
                console.log('unhandled', e);
                break;
        }
    };

    chatSocket.onclose = reconnetIfNeed;
}