/**
 * Titan Message Renderer — markdown, code blocks, timestamps (Phase 17.5)
 */
(function (global) {
  "use strict";

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatTimestamp(iso) {
    if (!iso) {
      return "";
    }
    try {
      var date = new Date(iso);
      return date.toLocaleTimeString("fr-FR", {
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_err) {
      return "";
    }
  }

  function renderInlineMarkdown(text) {
    var html = escapeHtml(text);
    html = html.replace(/`([^`]+)`/g, "<code class=\"tdl-md-code\">$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    html = html.replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      "<a href=\"$2\" target=\"_blank\" rel=\"noopener noreferrer\" class=\"tdl-md-link\">$1</a>"
    );
    return html;
  }

  function renderMarkdown(source) {
    if (!source) {
      return "";
    }

    var lines = String(source).split("\n");
    var htmlParts = [];
    var i = 0;

    while (i < lines.length) {
      var line = lines[i];

      if (/^```/.test(line)) {
        var lang = line.slice(3).trim();
        var codeLines = [];
        i += 1;
        while (i < lines.length && !/^```/.test(lines[i])) {
          codeLines.push(lines[i]);
          i += 1;
        }
        i += 1;
        htmlParts.push(
          "<div class=\"tdl-md-pre-wrap\">" +
            "<div class=\"tdl-md-pre-header\">" +
              "<span class=\"tdl-md-pre-lang\">" +
                escapeHtml(lang || "code") +
              "</span>" +
              "<button type=\"button\" class=\"tdl-md-copy\" data-copy-target=\"code\" aria-label=\"Copier\">Copier</button>" +
            "</div>" +
            "<pre class=\"tdl-md-pre\"><code>" +
              escapeHtml(codeLines.join("\n")) +
            "</code></pre>" +
          "</div>"
        );
        continue;
      }

      if (/^\|.+\|$/.test(line.trim())) {
        var tableRows = [];
        while (i < lines.length && /^\|.+\|$/.test(lines[i].trim())) {
          tableRows.push(lines[i].trim());
          i += 1;
        }
        if (tableRows.length >= 2 && /^\|[\s\-:|]+\|$/.test(tableRows[1])) {
          var headerCells = tableRows[0]
            .slice(1, -1)
            .split("|")
            .map(function (c) {
              return c.trim();
            });
          var bodyRows = tableRows.slice(2);
          var thead =
            "<thead><tr>" +
            headerCells
              .map(function (c) {
                return "<th>" + renderInlineMarkdown(c) + "</th>";
              })
              .join("") +
            "</tr></thead>";
          var tbody =
            "<tbody>" +
            bodyRows
              .map(function (row) {
                var cells = row
                  .slice(1, -1)
                  .split("|")
                  .map(function (c) {
                    return c.trim();
                  });
                return (
                  "<tr>" +
                  cells
                    .map(function (c) {
                      return "<td>" + renderInlineMarkdown(c) + "</td>";
                    })
                    .join("") +
                  "</tr>"
                );
              })
              .join("") +
            "</tbody>";
          htmlParts.push(
            "<div class=\"tdl-md-table-wrap\"><table class=\"tdl-md-table\">" +
              thead +
              tbody +
              "</table></div>"
          );
        } else {
          htmlParts.push("<p>" + renderInlineMarkdown(line) + "</p>");
          i += 1;
        }
        continue;
      }

      if (/^#{1,3}\s/.test(line)) {
        var level = line.match(/^(#+)/)[1].length;
        var headingText = line.replace(/^#+\s*/, "");
        htmlParts.push(
          "<h" +
            level +
            " class=\"tdl-md-h" +
            level +
            "\">" +
            renderInlineMarkdown(headingText) +
            "</h" +
            level +
            ">"
        );
        i += 1;
        continue;
      }

      if (/^[-*]\s/.test(line)) {
        var listItems = [];
        while (i < lines.length && /^[-*]\s/.test(lines[i])) {
          listItems.push(lines[i].replace(/^[-*]\s/, ""));
          i += 1;
        }
        htmlParts.push(
          "<ul class=\"tdl-md-list\">" +
            listItems
              .map(function (item) {
                return "<li>" + renderInlineMarkdown(item) + "</li>";
              })
              .join("") +
            "</ul>"
        );
        continue;
      }

      if (/^\d+\.\s/.test(line)) {
        var orderedItems = [];
        while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
          orderedItems.push(lines[i].replace(/^\d+\.\s/, ""));
          i += 1;
        }
        htmlParts.push(
          "<ol class=\"tdl-md-list tdl-md-list--ordered\">" +
            orderedItems
              .map(function (item) {
                return "<li>" + renderInlineMarkdown(item) + "</li>";
              })
              .join("") +
            "</ol>"
        );
        continue;
      }

      if (line.trim() === "") {
        i += 1;
        continue;
      }

      htmlParts.push("<p>" + renderInlineMarkdown(line) + "</p>");
      i += 1;
    }

    return htmlParts.join("");
  }

  function MessageRenderer(options) {
    this.container = options.container;
    this.onCopy = options.onCopy || null;
  }

  MessageRenderer.prototype.createMessageElement = function (message) {
    var isUser = message.role === "user";
    var isTitan = message.role === "titan" || message.role === "assistant";

    var block = document.createElement("article");
    block.className =
      "tdl-msg" +
      (isUser ? " tdl-msg--user" : "") +
      (isTitan ? " tdl-msg--titan" : "") +
      (message.status === "streaming" ? " tdl-msg--streaming" : "") +
      (message.status === "interrupted" ? " tdl-msg--interrupted" : "");
    block.dataset.messageId = message.id;
    block.setAttribute("role", "article");

    var meta = document.createElement("div");
    meta.className = "tdl-msg__meta";

    var author = document.createElement("span");
    author.className = "tdl-msg__author";
    author.textContent = isUser ? "Toi" : "Titan";

    var time = document.createElement("time");
    time.className = "tdl-msg__time";
    time.dateTime = message.timestamp || "";
    time.textContent = formatTimestamp(message.timestamp);

    meta.appendChild(author);
    meta.appendChild(time);

    var body = document.createElement("div");
    body.className = "tdl-msg__body tdl-md";

    if (isUser) {
      body.textContent = message.content || "";
    } else {
      body.innerHTML = renderMarkdown(message.content || "");
      this._bindCopyButtons(body);
    }

    block.appendChild(meta);
    block.appendChild(body);

    requestAnimationFrame(function () {
      block.classList.add("tdl-msg--visible");
    });

    return block;
  };

  MessageRenderer.prototype.updateMessageContent = function (element, content, role) {
    var body = element.querySelector(".tdl-msg__body");
    if (!body) {
      return;
    }
    if (role === "user") {
      body.textContent = content;
    } else {
      body.innerHTML = renderMarkdown(content);
      this._bindCopyButtons(body);
    }
  };

  MessageRenderer.prototype.setStreamingState = function (element, streaming) {
    element.classList.toggle("tdl-msg--streaming", streaming);
  };

  MessageRenderer.prototype._bindCopyButtons = function (root) {
    var self = this;
    root.querySelectorAll(".tdl-md-copy").forEach(function (btn) {
      if (btn.dataset.bound) {
        return;
      }
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {
        var pre = btn.closest(".tdl-md-pre-wrap");
        var code = pre && pre.querySelector("code");
        if (!code) {
          return;
        }
        var text = code.textContent || "";
        navigator.clipboard
          .writeText(text)
          .then(function () {
            btn.textContent = "Copié";
            setTimeout(function () {
              btn.textContent = "Copier";
            }, 1600);
            if (self.onCopy) {
              self.onCopy(text);
            }
          })
          .catch(function () {
            btn.textContent = "Erreur";
          });
      });
    });
  };

  MessageRenderer.prototype.renderAll = function (messages) {
    if (!this.container) {
      return;
    }
    this.container.innerHTML = "";
    var self = this;
    messages.forEach(function (msg) {
      var el = self.createMessageElement(msg);
      el.classList.add("tdl-msg--visible");
      self.container.appendChild(el);
    });
  };

  MessageRenderer.prototype.append = function (message) {
    if (!this.container) {
      return null;
    }
    var el = this.createMessageElement(message);
    this.container.appendChild(el);
    return el;
  };

  MessageRenderer.prototype.scrollToBottom = function (smooth) {
    var scrollParent = this.container && this.container.closest(".tdl-conversation__scroll");
    if (!scrollParent) {
      return;
    }
    scrollParent.scrollTo({
      top: scrollParent.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  };

  MessageRenderer.prototype.findElement = function (messageId) {
    if (!this.container) {
      return null;
    }
    return this.container.querySelector('[data-message-id="' + messageId + '"]');
  };

  global.TitanMessageRenderer = MessageRenderer;
  global.TitanMessageRendererUtils = {
    renderMarkdown: renderMarkdown,
    formatTimestamp: formatTimestamp,
  };
})(window);
