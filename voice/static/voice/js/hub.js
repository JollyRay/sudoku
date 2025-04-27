document.addEventListener('DOMContentLoaded', (event) => {

    const groupsNav = document.querySelectorAll('.group-list > div:nth-child(n+2)');

    groupsNav.forEach(group => {
        group.addEventListener('click', (event) => {
            hideCurrentInfo()

            const groupName = event.currentTarget?.getAttribute('name');
            const newGroupInfoItem = document.querySelector(`.group-info-item[name="${groupName}"]`);
            newGroupInfoItem.classList.remove('hidden');
            
        });
    });

    const newRoom = document.querySelector('.group-list > div:first-child');
    
    newRoom.addEventListener('click', event => {
        hideCurrentInfo();
        const newRoomForm = document.querySelector('.group-info > div:first-child');
        newRoomForm.classList.remove('hidden');
    });
    
});

function hideCurrentInfo(){
    const oldGropuInfoItem = document.querySelector('.group-info > div:not(.hidden)');
    oldGropuInfoItem?.classList.add('hidden');
}