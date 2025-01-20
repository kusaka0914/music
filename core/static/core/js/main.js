// コメントの表示/非表示を切り替える
function toggleComments(postId) {
    const commentsSection = document.getElementById(`comments-${postId}`);
    const commentButton = document.querySelector(`button[data-post-id="${postId}"].comment-button`);
    const commentText = commentButton.querySelector('.comment-text');
    
    if (commentsSection.style.display === 'none') {
        commentsSection.style.display = 'block';
        commentText.textContent = 'コメントを非表示';
    } else {
        commentsSection.style.display = 'none';
        commentText.textContent = 'コメントを表示';
    }
}

// コメントを送信する
async function submitComment(event, postId) {
    event.preventDefault();
    const form = event.target;
    const input = form.querySelector('input[name="comment"]');
    const content = input.value.trim();
    
    if (!content) return;
    
    try {
        const response = await fetch(`/add-comment/${postId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ content })
        });
        
        if (!response.ok) throw new Error('コメントの送信に失敗しました');
        
        const data = await response.json();
        const commentsList = document.querySelector(`#comments-${postId} .comments-list`);
        
        // 新しいコメントを追加
        const commentHtml = `
            <div class="comment">
                <div class="comment-user">
                    <img src="${data.user_avatar || '/static/images/default-avatar.svg'}" 
                         alt="${data.username}">
                    <div class="comment-content">
                        <div class="comment-header">
                            <span class="comment-username">${data.username}</span>
                            <span class="comment-time">たった今</span>
                        </div>
                        <p class="comment-text">${data.content}</p>
                    </div>
                </div>
            </div>
        `;
        commentsList.insertAdjacentHTML('beforeend', commentHtml);
        
        // コメント数を更新
        const countElement = document.querySelector(`button[data-post-id="${postId}"].comment-button .comment-count`);
        countElement.textContent = parseInt(countElement.textContent) + 1;
        
        // 入力フィールドをクリア
        input.value = '';
        
    } catch (error) {
        console.error('Error:', error);
        alert('コメントの送信に失敗しました。もう一度お試しください。');
    }
}

// いいねボタンのクリックイベント
document.querySelectorAll('.like-button').forEach(button => {
    button.addEventListener('click', async () => {
        const postId = button.dataset.postId;
        const icon = button.querySelector('i');
        const countElement = button.querySelector('.like-count');
        
        try {
            const response = await fetch(`/like-post/${postId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken')
                }
            });
            
            if (!response.ok) throw new Error('いいねの処理に失敗しました');
            
            const data = await response.json();
            
            // いいねの状態を更新
            if (data.liked) {
                button.classList.add('liked');
                icon.classList.remove('bi-heart');
                icon.classList.add('bi-heart-fill');
            } else {
                button.classList.remove('liked');
                icon.classList.remove('bi-heart-fill');
                icon.classList.add('bi-heart');
            }
            
            // いいね数を更新
            countElement.textContent = data.likes_count;
            
        } catch (error) {
            console.error('Error:', error);
            alert('いいねの処理に失敗しました。もう一度お試しください。');
        }
    });
});

// CSRFトークンを取得する関数
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
} 