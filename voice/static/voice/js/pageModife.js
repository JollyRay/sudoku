document.getElementById('local-screen-video').addEventListener('click', toggleFullscreen);

function createNewVideoElement(nick, isScreen = false, homeElemnt = undefined){
    homeElemnt = homeElemnt || document.getElementById('video-home');

    let videoElement = document.createElement('video');
    videoElement.classList.add("webrtc-video");
    videoElement.setAttribute('playsinline', '');
    videoElement.setAttribute('autoplay', true);
    videoElement.setAttribute('nick', nick);
    videoElement.setAttribute('is-screen', isScreen);

    if (isScreen){
        videoElement.addEventListener('click', toggleFullscreen);
    }

    homeElemnt.appendChild(videoElement);

    return videoElement;
}

function toggleScreenVideo(screenElement){
    screenElement = screenElement || document.getElementById('local-screen-video');
    screenElement.classList.toggle('hidden');

    rerender(screenElement);
}

function isExist(nick) {
    return nick == selfNick || document.querySelectorAll(`video[nick="${nick}"]`).length > 0;
}

function removeVideo(nick, isScreen = undefined){
    if (isScreen == undefined){
        document.querySelectorAll(`video[nick="${nick}"]`).forEach(elem => {
            elem.remove()
        });
    } else {
        document.querySelectorAll(`video[nick="${nick}"][is-screen=${isScreen}]`).forEach(elem => {
            elem.remove()
        });
    }
}

function rerender(element){
    let tempDisplay = element.style.display;
    element.style.display = tempDisplay == 'none' ? '' : 'none';
    element.style.display = tempDisplay;
}

function toggleFullscreen(event) {
    let videoElement = event.target;
    if (!document.fullscreenElement) {
        if (videoElement.requestFullscreen) {
            videoElement.requestFullscreen();
        } else if (videoElement.webkitRequestFullscreen) { /* Safari */
            videoElement.webkitRequestFullscreen();
        } else if (videoElement.msRequestFullscreen) { /* IE11 */
            videoElement.msRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) { /* Safari */
            document.webkitExitFullscreen();
        } else if (document.msExitFullscreen) { /* IE11 */
            document.msExitFullscreen();
        }
    }
}