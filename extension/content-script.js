(function () {
  if (window.__stakedMediaCopilotBridgeLoaded) {
    return;
  }
  window.__stakedMediaCopilotBridgeLoaded = true;

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type === "get_composer_state") {
      sendResponse(getComposerState());
      return false;
    }

    if (message?.type === "insert_text") {
      try {
        insertIntoComposer(assertNonEmpty(message?.payload?.text, "text"));
        sendResponse({ ok: true });
      } catch (error) {
        sendResponse({
          ok: false,
          error: {
            message: String(error?.message || error || "Insert failed")
          }
        });
      }
      return false;
    }

    return false;
  });

  function getComposerState() {
    const composer = findComposer();
    return {
      available: Boolean(composer),
      message: composer ? "Composer detected" : "Open the X composer to insert drafts."
    };
  }

  function findComposer() {
    const selectors = [
      '[data-testid="tweetTextarea_0"][contenteditable="true"]',
      'div[role="textbox"][contenteditable="true"][data-testid*="tweetTextarea"]',
      'div[role="textbox"][contenteditable="true"][aria-label]'
    ];
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        return element;
      }
    }
    return null;
  }

  function insertIntoComposer(text) {
    const composer = findComposer();
    if (!composer) {
      throw new Error("X composer not found. Open the composer first.");
    }

    composer.focus();
    const selection = window.getSelection();
    if (!selection) {
      composer.textContent = text;
      dispatchComposerInput(composer, text);
      composer.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }

    const range = document.createRange();
    range.selectNodeContents(composer);
    selection.removeAllRanges();
    selection.addRange(range);
    range.deleteContents();

    const textNode = document.createTextNode(text);
    range.insertNode(textNode);
    range.setStartAfter(textNode);
    range.collapse(true);
    selection.removeAllRanges();
    selection.addRange(range);

    dispatchComposerInput(composer, text);
    composer.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function dispatchComposerInput(composer, text) {
    composer.dispatchEvent(
      new InputEvent("beforeinput", {
        bubbles: true,
        cancelable: true,
        inputType: "insertText",
        data: text
      })
    );
    composer.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        cancelable: true,
        inputType: "insertText",
        data: text
      })
    );
  }

  function assertNonEmpty(value, name) {
    const normalized = String(value || "").trim();
    if (!normalized) {
      throw new Error(`${name} is required`);
    }
    return normalized;
  }
})();
