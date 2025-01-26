document.addEventListener('DOMContentLoaded', function() {
    // いいねボタンの処理
    function setupLikeButtons() {
        document.querySelectorAll('.like-button').forEach(button => {
            // イベントリスナーが既に設定されている場合はスキップ
            if (button.dataset.hasListener === 'true') {
                return;
            }
            
            button.dataset.hasListener = 'true';
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                const postId = this.dataset.postId;
                if (!postId) {
                    return;
                }

                // ボタンの状態を即座に視覚的に更新
                const icon = this.querySelector('i');
                const actionGroup = this.closest('.action-group');
                const countSpan = actionGroup.querySelector('.like-count');
                const currentCount = parseInt(countSpan.textContent) || 0;
                
                if (this.classList.contains('liked')) {
                    this.classList.remove('liked');
                    icon.classList.remove('bi-heart-fill');
                    icon.classList.add('bi-heart');
                    countSpan.textContent = `${Math.max(0, currentCount - 1)}人がいいね`;
                } else {
                    this.classList.add('liked');
                    icon.classList.remove('bi-heart');
                    icon.classList.add('bi-heart-fill');
                    countSpan.textContent = `${currentCount + 1}人がいいね`;
                }

                // サーバーにリクエストを送信
                fetch(`/post/${postId}/like/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken'),
                        'Content-Type': 'application/json'
                    }
                });
            });
        });
    }

    // いいねモーダルの処理を追加
    window.showLikesModal = async function(postId) {
        try {
            const response = await fetch(`/api/posts/${postId}/likes/`);
            const data = await response.json();
            
            const modal = new bootstrap.Modal(document.getElementById('likesModal'));
            const userList = document.querySelector('.likes-list');
            userList.innerHTML = '';

            if (data.users.length === 0) {
                userList.innerHTML = `
                    <div class="no-users">
                        <p>まだいいねしたユーザーはいません</p>
                    </div>
                `;
            } else {
                data.users.forEach(user => {
                    const userItem = document.createElement('div');
                    userItem.className = 'user-item';
                    userItem.innerHTML = `
                    <a href="/profile/${user.username}/" class="username">
                        <div class="modal-user-info">
                            <img src="${user.avatar || '/static/images/default-avatar.svg'}" alt="${user.username}" class="user-avatar">
                            <div class="user-details">
                                ${user.username}
                                <span class="user-meta">${user.name || ''}</span>
                            </div>
                        </div>
                    </a>
                    `;
                    userList.appendChild(userItem);
                });
            }
            
            modal.show();
        } catch (error) {
            console.error('Error:', error);
        }
    };

    // コメントボタンの処理
    function setupCommentButtons() {
        document.querySelectorAll('.comment-button').forEach(button => {
            if (button.dataset.hasListener === 'true') {
                return;
            }
            
            button.dataset.hasListener = 'true';
            button.addEventListener('click', function() {
                const postId = this.dataset.postId;
                const commentsSection = document.querySelector(`#comments-${postId}`);
                if (commentsSection) {
                    const isHidden = commentsSection.style.display === 'none';
                    commentsSection.style.display = isHidden ? 'block' : 'none';
                    const textSpan = this.querySelector('.comment-text');
                    if (textSpan) {
                        textSpan.textContent = isHidden ? 'コメントを非表示' : 'コメントを表示';
                    }
                }
            });
        });
    }

    // スタイルを追加
    const style = document.createElement('style');
    style.textContent = `
        .action-group {
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }
        .like-button {
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            background: none;
            border: none;
            color: #b3b3b3;
            cursor: pointer;
            padding: 0.5rem;
        }
        .like-animation {
            transform: scale(1.2);
        }
        .like-button.liked {
            color: #1DB954;
        }
        .like-button.liked i {
            color: #1DB954;
        }
        .likes-list-button {
            background: none;
            border: none;
            color: #b3b3b3;
            cursor: pointer;
            padding: 0.5rem;
            transition: color 0.3s;
            font-size: 0.875rem;
        }
        .likes-list-button:hover {
            color: #fff;
            text-decoration: underline;
        }
    `;
    document.head.appendChild(style);

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

    // 初期設定
    setupLikeButtons();
    setupCommentButtons();

    // 動的に追加された要素に対する設定
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.addedNodes.length) {
                setupLikeButtons();
                setupCommentButtons();
            }
        });
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

    // アラートの自動非表示
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.classList.remove('show');
            setTimeout(() => alert.remove(), 150);
        }, 3000);
    });
}); 