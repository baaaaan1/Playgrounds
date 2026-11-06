from __future__ import annotations

from dataclasses import replace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QMenu, QStyleOptionViewItem

from app.core.models import Conversation, Message
from app.ui import theme
from app.ui.sidebar import Sidebar


@pytest.fixture()
def sidebar(qt_app):
    widget = Sidebar(theme.tokens_for("dark"))
    widget.resize(280, 480)
    widget.show()
    qt_app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    qt_app.processEvents()


def _ids(sidebar: Sidebar) -> list[str]:
    return [
        sidebar._list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(sidebar._list.count())
    ]


def _search(sidebar: Sidebar, query: str) -> None:
    sidebar._search.setText(query)
    QTest.qWait(280)


def test_history_sorts_pinned_first_then_newest(sidebar) -> None:
    conversations = [
        Conversation(id="old", title="Old", updated_at=1),
        Conversation(id="new", title="New", updated_at=100),
        Conversation(id="pin-old", title="Pinned old", updated_at=2, pinned=True),
        Conversation(id="pin-new", title="Pinned new", updated_at=3, pinned=True),
        Conversation(id="archive", updated_at=200, pinned=True, archived=True),
    ]
    sidebar.set_conversations(conversations)
    assert _ids(sidebar) == ["pin-new", "pin-old", "new", "old"]
    assert sidebar._list.item(0).text() == "Pinned: Pinned new"
    assert sidebar._list.item(2).text() == "New"
    assert [conversation.id for conversation in conversations] == [
        "old", "new", "pin-old", "pin-new", "archive",
    ]


def test_title_search_is_case_insensitive_and_debounced(sidebar) -> None:
    sidebar.set_conversations([
        Conversation(id="match", title="Travel PLANS"),
        Conversation(id="other", title="Shopping"),
    ])
    sidebar._search.setText("not found")
    assert sidebar._search_timer.isSingleShot()
    assert sidebar._search_timer.interval() == 200
    assert len(_ids(sidebar)) == 2
    QTest.qWait(80)
    sidebar._search.setText("pLaNs")
    QTest.qWait(80)
    assert len(_ids(sidebar)) == 2
    QTest.qWait(200)
    assert _ids(sidebar) == ["match"]
    selected = QSignalSpy(sidebar.conversation_selected)
    message_selected = QSignalSpy(sidebar.search_result_selected)
    QTest.mouseClick(
        sidebar._list.viewport(), Qt.MouseButton.LeftButton,
        pos=sidebar._list.visualItemRect(sidebar._list.item(0)).center(),
    )
    assert list(selected) == [["match"]]
    assert not message_selected


def test_message_search_emits_only_message_hit_and_original_query(sidebar) -> None:
    message = Message("assistant", "Prefix " * 20 + "<b>NEEDLE</b>\nresponse " * 30)
    conversation = Conversation(id="match", title="A saved title", messages=[message])
    sidebar.set_conversations([conversation, Conversation(title="Other")])
    _search(sidebar, "nEeDlE")
    assert _ids(sidebar) == [conversation.id]
    item = sidebar._list.item(0)
    assert item.data(Qt.ItemDataRole.UserRole + 1) == message.id
    assert "NEEDLE" in item.text()
    assert len(item.text()) < 180
    assert "&lt;b&gt;NEEDLE&lt;/b&gt;" in item.toolTip()
    assert "<b>NEEDLE</b>" not in item.toolTip()
    selected = QSignalSpy(sidebar.conversation_selected)
    message_selected = QSignalSpy(sidebar.search_result_selected)
    # A pending edit must not change the query attached to an already visible hit.
    sidebar._search.setText("different")
    QTest.mouseClick(
        sidebar._list.viewport(), Qt.MouseButton.LeftButton,
        pos=sidebar._list.visualItemRect(item).center(),
    )
    assert list(message_selected) == [[conversation.id, message.id, "nEeDlE"]]
    assert not selected
    assert conversation.title == "A saved title"
    assert "<b>NEEDLE</b>" in message.content


def test_search_includes_title_and_each_matching_message(sidebar) -> None:
    messages = [Message("user", "Needle one"), Message("assistant", "Second NEEDLE")]
    conversation = Conversation(id="chat", title="Needle title", messages=messages)
    sidebar.set_conversations([conversation])
    _search(sidebar, "needle")
    assert _ids(sidebar) == ["chat", "chat", "chat"]
    assert [
        sidebar._list.item(row).data(Qt.ItemDataRole.UserRole + 1)
        for row in range(sidebar._list.count())
    ] == ["", messages[0].id, messages[1].id]
    _search(sidebar, " \t ")
    assert _ids(sidebar) == ["chat"]


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
@pytest.mark.parametrize("message_hit", [False, True])
def test_keyboard_activates_once_without_opening_on_navigation(sidebar, key, message_hit) -> None:
    message = Message("assistant", "A NEEDLE message")
    sidebar.set_conversations([
        Conversation(id="chat", title="Saved", updated_at=1, messages=[message]),
        Conversation(id="other", title="Other", updated_at=2, messages=[Message("user", "needle")]),
    ])
    if message_hit:
        _search(sidebar, "nEeDlE")
    selected = QSignalSpy(sidebar.conversation_selected)
    message_selected = QSignalSpy(sidebar.search_result_selected)
    sidebar._list.setCurrentRow(0)
    sidebar._list.setFocus()
    QTest.keyClick(sidebar._list, Qt.Key.Key_Down)
    assert sidebar.current_id() == "chat"
    assert not selected
    assert not message_selected
    if message_hit:
        # Enter must use the query attached to the hit, not a pending search edit.
        sidebar._search.setText("different")
    QTest.keyClick(sidebar._list, key)
    assert list(message_selected) == ([["chat", message.id, "nEeDlE"]] if message_hit else [])
    assert list(selected) == ([] if message_hit else [["chat"]])


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_with_no_current_result_does_not_dispatch(sidebar, key) -> None:
    selected = QSignalSpy(sidebar.conversation_selected)
    message_selected = QSignalSpy(sidebar.search_result_selected)
    QTest.keyClick(sidebar._list, key)
    sidebar.set_conversations([Conversation(id="chat", title="Saved")])
    sidebar.select("chat")
    sidebar.clear_selection()
    QTest.keyClick(sidebar._list, key)
    assert not selected
    assert not message_selected


def test_enter_activates_current_item_even_without_selection(sidebar) -> None:
    sidebar.set_conversations([Conversation(id="chat", title="Saved")])
    sidebar._list.setCurrentRow(0)
    sidebar._list.clearSelection()
    selected = QSignalSpy(sidebar.conversation_selected)
    # Qt can focus a current row without selecting it when tabbing into the list.
    QTest.keyClick(sidebar._list, Qt.Key.Key_Return)
    assert list(selected) == [["chat"]]


def test_archive_button_navigates_in_existing_sidebar(sidebar, qt_app) -> None:
    button = sidebar._archived_button
    history = sidebar._list
    windows = set(qt_app.topLevelWidgets())
    assert not button.isCheckable()
    assert button.text() == "Open archive"
    assert button.accessibleName() == "Open archived chats"
    assert button.toolTip() == button.accessibleDescription()
    assert "in this sidebar" in button.toolTip()
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert sidebar._showing_archived
    assert button.text() == "Back"
    assert button.accessibleName() == "Back to history"
    assert button.toolTip() == button.accessibleDescription()
    assert sidebar._list.accessibleName() == "Archived chats"
    assert sidebar._list is history
    assert set(qt_app.topLevelWidgets()) == windows
    QTest.keyClick(button, Qt.Key.Key_Space)
    assert not sidebar._showing_archived
    assert button.text() == "Open archive"
    assert sidebar._list.accessibleName() == "Chat history"


def test_empty_states_and_accessible_result_counts(sidebar) -> None:
    assert sidebar._status.isVisible()
    assert sidebar._status.text() == "No chats yet."
    assert sidebar._status.accessibleDescription() == "0 chats"
    assert not sidebar._clear_search_button.isVisible()
    sidebar._archived_button.click()
    assert sidebar._status.text() == "No archived chats."
    sidebar._archived_button.click()
    sidebar.set_conversations([
        Conversation(id="chat", title="Needle title", messages=[Message("user", "needle body")]),
        Conversation(id="other", title="Other"),
    ])
    assert sidebar._status.text() == "2 chats"
    _search(sidebar, "needle")
    assert sidebar._status.text() == "2 search results"
    assert sidebar._status.accessibleName() == "2 search results"
    assert sidebar._list.accessibleDescription() == "2 search results"
    assert sidebar._clear_search_button.isVisible()
    _search(sidebar, "body")
    assert sidebar._status.text() == "1 search result"
    _search(sidebar, "missing")
    assert sidebar._status.text() == "No search results."
    assert sidebar._status.accessibleName() == "No search results."
    assert sidebar._status.accessibleDescription() == "0 search results"
    assert sidebar._list.accessibleDescription() == "0 search results"
    assert sidebar._list.count() == 0


def test_clear_search_is_immediate_and_keeps_archive_scope(sidebar, qt_app) -> None:
    sidebar.set_conversations([
        Conversation(id="active", title="Active"),
        Conversation(id="archived", title="Archived", archived=True),
    ])
    sidebar._archived_button.click()
    sidebar.select("archived")
    _search(sidebar, "missing")
    assert sidebar._status.text() == "No search results."
    selected = QSignalSpy(sidebar.conversation_selected)
    QTest.mouseClick(sidebar._clear_search_button, Qt.MouseButton.LeftButton)
    qt_app.processEvents()
    assert sidebar._search.text() == ""
    assert not sidebar._search_timer.isActive()
    assert not sidebar._clear_search_button.isVisible()
    assert sidebar._search.hasFocus()
    assert sidebar._showing_archived
    assert _ids(sidebar) == ["archived"]
    assert sidebar.current_id() == "archived"
    assert sidebar._status.text() == "1 chat"
    assert not selected
    # A clear action is also available before the debounce timer has fired.
    sidebar._search.setText("pending")
    assert sidebar._clear_search_button.isVisible()
    sidebar._clear_search_button.click()
    assert not sidebar._search_timer.isActive()
    assert _ids(sidebar) == ["archived"]


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_search_delegate_uses_two_native_plain_text_lines(sidebar, qt_app, mode) -> None:
    sidebar.setStyleSheet(theme.build_qss(theme.tokens_for(mode)))
    sidebar.resize(210, 480)
    message = Message("user", "line\nNEEDLE <b>literal</b>")
    sidebar.set_conversations([
        Conversation(id="chat", title="Needle <title>", pinned=True, messages=[message]),
    ])
    _search(sidebar, "needle")
    qt_app.processEvents()
    title_item, hit = sidebar._list.item(0), sidebar._list.item(1)
    option = QStyleOptionViewItem()
    option.initFrom(sidebar._list)
    option.widget = sidebar._list
    sidebar._list.itemDelegate().initStyleOption(option, sidebar._list.indexFromItem(hit))
    assert option.text.split("\u2028") == [
        "Pinned: Needle <title>", "line NEEDLE <b>literal</b>",
    ]
    assert sidebar._list.visualItemRect(hit).height() > sidebar._list.visualItemRect(title_item).height()
    assert sidebar._list.horizontalScrollBar().maximum() == 0
    assert hit.data(Qt.ItemDataRole.AccessibleTextRole) == hit.text()
    assert "Needle <title>" in hit.text()
    assert "line NEEDLE <b>literal</b>" in hit.text()
    assert hit.data(Qt.ItemDataRole.UserRole) == "chat"
    assert hit.data(Qt.ItemDataRole.UserRole + 1) == message.id
    assert hit.data(Qt.ItemDataRole.UserRole + 2) == "needle"


def test_archived_view_scopes_search_and_refresh(sidebar) -> None:
    active = Conversation(id="active", title="Needle active")
    archived = Conversation(
        id="archived", title="Saved", archived=True,
        messages=[Message("user", "Needle archived")],
    )
    sidebar.set_conversations([active, archived])
    assert not sidebar._showing_archived
    assert _ids(sidebar) == [active.id]
    _search(sidebar, "needle")
    sidebar._archived_button.click()
    assert sidebar._section.text() == "ARCHIVED"
    assert _ids(sidebar) == [archived.id]
    assert sidebar._search.text() == "needle"
    sidebar.set_conversations([active, replace(archived, archived=False)])
    assert _ids(sidebar) == []
    assert sidebar._showing_archived
    sidebar._archived_button.click()
    assert set(_ids(sidebar)) == {active.id, archived.id}
    assert sidebar._section.text() == "HISTORY"


@pytest.mark.parametrize("action, pinned, archived, signal, expected", [
    ("Rename", False, False, "rename_requested", ["chat"]),
    ("Pin", False, False, "pin_requested", ["chat", True]),
    ("Unpin", True, False, "pin_requested", ["chat", False]),
    ("Archive", False, False, "archive_requested", ["chat", True]),
    ("Unarchive", True, True, "archive_requested", ["chat", False]),
    ("Delete", False, True, "delete_requested", ["chat"]),
])
def test_context_menu_requests_without_mutating(
    sidebar, monkeypatch, action, pinned, archived, signal, expected,
) -> None:
    conversation = Conversation(id="chat", title="User <title>", pinned=pinned, archived=archived)
    sidebar.set_conversations([conversation])
    sidebar.show_archived(archived)
    observed = QSignalSpy(getattr(sidebar, signal))
    selected = QSignalSpy(sidebar.conversation_selected)

    def choose(menu, position):
        actions = {item.text(): item for item in menu.actions() if not item.isSeparator()}
        assert set(actions) == {
            "Rename", "Unpin" if pinned else "Pin",
            "Unarchive" if archived else "Archive", "Delete",
        }
        return actions[action]

    monkeypatch.setattr(QMenu, "exec", choose)
    sidebar._on_context_menu(sidebar._list.visualItemRect(sidebar._list.item(0)).center())
    assert list(observed) == [expected]
    assert not selected
    assert conversation.pinned == pinned
    assert conversation.archived == archived
    assert conversation.title == "User <title>"


def test_refresh_preserves_exact_message_selection_query_and_scroll(sidebar, qt_app) -> None:
    conversations = [
        Conversation(
            id=f"chat-{index}", title=f"Chat {index}", updated_at=index,
            messages=[Message("user", "needle first"), Message("assistant", "needle second")],
        )
        for index in range(40)
    ]
    sidebar.set_conversations(conversations)
    _search(sidebar, "needle")
    item = sidebar._list.item(31)
    sidebar._list.setCurrentItem(item)
    selected_id = sidebar.current_id()
    message_id = item.data(Qt.ItemDataRole.UserRole + 1)
    scrollbar = sidebar._list.verticalScrollBar()
    assert scrollbar.maximum() > 0
    scrollbar.setValue(scrollbar.maximum() // 2)
    scroll = scrollbar.value()
    opened = QSignalSpy(sidebar.conversation_selected)
    message_opened = QSignalSpy(sidebar.search_result_selected)
    sidebar.set_conversations([replace(chat, title=chat.title + " renamed") for chat in conversations])
    qt_app.processEvents()
    assert sidebar._search.text() == "needle"
    assert sidebar.current_id() == selected_id
    assert sidebar._list.currentItem().data(Qt.ItemDataRole.UserRole + 1) == message_id
    assert scrollbar.value() == scroll
    assert not opened
    assert not message_opened
    sidebar.select(selected_id)
    assert sidebar._list.currentItem().data(Qt.ItemDataRole.UserRole + 1) == message_id


def test_hidden_selection_restores_and_clear_selection_stays_cleared(sidebar) -> None:
    conversation = Conversation(id="chat", title="A title")
    sidebar.set_conversations([conversation])
    sidebar.select(conversation.id)
    assert sidebar.current_id() == conversation.id
    _search(sidebar, "no matches")
    assert sidebar.current_id() is None
    sidebar.set_conversations([replace(conversation, title="Another title")])
    assert sidebar._search.text() == "no matches"
    _search(sidebar, "")
    assert sidebar.current_id() == conversation.id
    sidebar.select("missing")
    assert sidebar.current_id() is None
    sidebar.select(conversation.id)
    sidebar.clear_selection()
    sidebar.set_conversations([conversation])
    assert sidebar.current_id() is None


def test_presentation_preserves_custom_titles_and_translates_sentinel(sidebar, monkeypatch) -> None:
    monkeypatch.setattr(Sidebar, "tr", lambda self, source: "Translated " + source)
    sidebar.set_conversations([
        Conversation(id="default", title="New chat", updated_at=3),
        Conversation(id="custom", title="New chat", title_is_custom=True, updated_at=2),
        Conversation(id="user", title="User <b>title</b>", updated_at=1),
    ])
    assert [sidebar._list.item(row).text() for row in range(3)] == [
        "Translated New chat", "New chat", "User <b>title</b>",
    ]
    assert "User &lt;b&gt;title&lt;/b&gt;" in sidebar._list.item(2).toolTip()


@pytest.mark.parametrize("key,modifiers", [
    (Qt.Key.Key_Menu, Qt.KeyboardModifier.NoModifier),
    (Qt.Key.Key_F10, Qt.KeyboardModifier.ShiftModifier),
])
def test_keyboard_can_open_conversation_actions(sidebar, monkeypatch, key, modifiers):
    sidebar.set_conversations([Conversation(id="chat", title="Keyboard chat")])
    sidebar._list.setCurrentRow(0)
    renamed = QSignalSpy(sidebar.rename_requested)
    opened = QSignalSpy(sidebar.conversation_selected)
    monkeypatch.setattr(QMenu, "exec", lambda menu, position: menu.actions()[0])
    QTest.keyClick(sidebar._list, key, modifiers)
    assert list(renamed) == [["chat"]]
    assert not opened
