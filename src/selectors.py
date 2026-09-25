"""抖音私信页面 CSS 选择器常量。

所有选择器按优先级排列，前面的优先匹配。每组选择器都提供了
多个备选项，以应对抖音前端页面结构的变化。
"""

# ===== 搜索相关 =====

# 搜索框
SEARCH_INPUTS = ('input[placeholder*="搜索"]',)

# 搜索结果项容器
SEARCH_ITEM_SELECTORS = (
    "[class*='SearchPanelitembox']",
    "[class*='SearchPanelitem-box']",
    "[class*='SearchPanelitem_box']",
    '[class*="SearchPanelitem"]',
    '[class*="searchPanelItem"]',
    '[class*="SearchItem"]',
    '[class*="search-item"]',
    '[class*="conversationSearchItem"]',
)

# 搜索结果标题
SEARCH_ITEM_TITLE_SELECTORS = (
    "[class*='SearchPanelitemtitle']",
    "[class*='SearchPanelitemTitle']",
    "[class*='SearchPanelitem_title']",
    "[class*='SearchPanelitem-title']",
    "[class*='SearchPanelitemname']",
    "[class*='SearchPanelitemName']",
    "[class*='SearchPanelitem_name']",
    "[class*='SearchPanelitem-name']",
    '[class*="SearchPanelitemsearch_highlight"]',
    '[class*="conversationConversationItemtitle"]',
)

# 搜索结果中的聊天按钮
SEARCH_ITEM_CHAT_BTN = "[class*='SearchPanelitemchat_btn']"

# 搜索用户头像
SEARCH_USER_AVATAR = '[class*="SearchPanelitemAvatar"]'

# 用户列表
USER_LIST_HEADER = '[class*="conversationConversationListHeader"]'

# ===== 会话行相关 =====

# 会话行
CONVERSATION_ROW_SELECTORS = (
    '[data-e2e="conversation-item"]',
    "[class*='conversationConversationItem']",
    "[class*='conversation-item']",
    "[class*='ConversationItem']",
)

# 会话标题
CONVERSATION_TITLE_SELECTORS = (
    "[class*='conversationConversationItemtitle']",
    "[class*='ConversationItemtitle']",
    "[class*='ConversationItemTitle']",
    "[class*='conversation-item-title']",
    "[class*='conversation-item-Title']",
    '[class="conversationConversationItemtitle"]',
)

# 会话时间
CONVERSATION_TIME_SELECTORS = (
    '[class*="ConversationItemTagNextToTitletimeStr"]',
)

# 会话描述
CONVERSATION_DESC_SELECTORS = (
    '[class*="ConversationItemDesc"]',
)

# ===== 聊天面板 =====

# 聊天面板标记
CHAT_PANEL_MARKERS = (
    '[class*="RightPanel"]',
    '[class*="chat-panel"]',
    '[class*="ChatContent"]',
)

# 聊天标题
CHAT_TITLE_SELECTORS = (
    "[class*='RightPanelHeadertitle']",
    "[class*='RightPanelHeaderTitle']",
    "[class*='RightPanelHeader_title']",
    "[class*='RightPanelHeader-title']",
    "[class*='chatHeadertitle']",
    "[class*='ChatHeaderTitle']",
    "[class*='chatHeader_title']",
    "[class*='ChatHeader-title']",
    '[class*="chat_panel_title"]',
)

# 消息输入框
MESSAGE_INPUTS = (
    '[class*="public-DraftEditor-content"]',
    '[contenteditable="true"]',
)

# 发送按钮（单数，向后兼容）
SEND_BUTTON = '[class*="messageMsgInputpublishBtn"]'

# 发送按钮（复数 tuple，优先匹配）
SEND_BUTTONS = (
    '[class*="messageMsgInputpublishBtn"]',
    '[class*="e2e-send-msg-btn"]',
    "[aria-label*='发送']",
    "button[aria-label*='发送']",
    "[role='button'][aria-label*='发送']",
)

# 表情按钮选择器
STICKER_BUTTONS = (
    '[class*="messageMsgInputiconAction"]',
    "svg[class*='iconAction']",
    "button[aria-label*='表情']",
    "[role='button'][aria-label*='表情']",
    "[title*='表情']",
)

# 表情面板选择器
STICKER_PANELS = (
    "[class*='emojiPanel']",
    "[class*='componentsemoji']",
    "[role='dialog']",
    "[class*='sticker']",
)

# 表情项
STICKER_ITEM_SELECTOR = ".emojiEmojiItememojiItem"
STICKER_ITEM_DESC_SELECTOR = ".emojiEmojiItememojiItemDesc"

# ===== 在线状态 =====

# 在线绿点
ONLINE_DOT_SELECTOR = '[class*="IMAvatarOnlineactiveDot"]'

# 头像容器
AVATAR_CONTAINER_SELECTOR = '[class*="commonIMAvataravatarContainer"]'

# 聊天面板在线状态选择器
CHAT_PANEL_STATUS_SELECTORS = (
    '[class*="RightPanelHeaderactiveTagOnline"]',
    '[class*="RightPanelHeaderactiveTagOffline"]',
    '[class*="RightPanelHeaderactiveTag"]',
)

# ===== 火花信息 =====

# 火花容器
STREAK_CONTAINER_SELECTOR = '[class*="commonStreakstreakContainer"]'

# 火花文本
STREAK_TEXT_SELECTORS = (
    '[class*="commonStreaknormalText commonStreaklabelText"]',
    '[class*="commonStreaknormalText"]',
    '[class*="commonStreaklabelText"]',
)

# 聊天面板中火花信息
CHAT_PANEL_STREAK_SELECTORS = (
    '[class*="RightPanelHeader"] [class*="commonStreaknormalText"]',
    '[class*="RightPanelHeader"] [class*="commonStreak"]',
)

# ===== 发送状态确认 =====

# 最新已发送消息定位器
LATEST_OUTGOING_MESSAGE = (
    '.messageMessageListlist [data-index="0"] '
    ".messageMessageBoxmessageBox:has("
    ".messageMessageBoxcontentBox.messageMessageBoxisFromMe)"
)

# 发送失败标记
SEND_FAILURE_MARKERS = (
    "text=发送失败",
    "[aria-label*='重试']",
    "[title*='重试']",
    "[class*='sendFailed']",
    "[class*='SendFailed']",
    "[class*='ContentSideSendStatusretry']",
    "[class*='SendStatusretry']",
)

# 发送中（pending spinner）标记
SEND_PENDING_MARKERS = (
    ".semi-spin",
    "[class*='im-saas-message-spin']",
    "[data-icon='spin']",
)

# 发送重试标记
SEND_RETRY_MARKERS = (
    "[aria-label*='重试']",
    "[title*='重试']",
    "[class*='ContentSideSendStatusretry']",
    "[class*='SendStatusretry']",
)
