// Injected into the Vesktop page over the Chrome DevTools Protocol.
// Evaluates to an object of helper functions; main.py caches it on window.
// Uses Discord's own internal stores/actions through Vencord's webpack helpers.
(() => {
    const W = Vencord.Webpack;
    const C = W.Common;
    const U = Vencord.Util;
    // Discord's internal pieces, found by name. A Discord update can rename one: then it's null, the features
    // that need it stop working, and health() says which, while everything else keeps working.
    const find = (...props) => { try { return W.findByProps(...props) ?? null; } catch { return null; } };
    const Voice = find("toggleSelfMute", "toggleSelfDeaf");
    const EmojiData = find("getByName", "convertNameToSurrogate");
    const EmojiUtils = find("getEmojiUnavailableReason");
    const Parser = find("parse", "parsePreprocessor");
    const Typing = find("startTyping", "stopTyping");
    const VoiceChannels = find("disconnect", "selectVoiceChannel");
    const Speaking = find("isSpeaking", "getSpeakingDuration") ?? find("isSpeaking");
    const ThreadActions = find("loadArchivedThreads", "joinThread");
    const store = name => { try { return W.findStore(name) ?? null; } catch { return null; } };
    const ChannelList = store("ChannelListStore"); // Discord's sidebar, as it draws it
    const ActiveThreads = store("ActiveThreadsStore");
    const JoinedThreads = store("ActiveJoinedThreadsStore");
    const ArchivedThreads = store("ArchivedThreadsStore");
    const PostUnreadCounts = store("ForumPostUnreadCountStore");
    let StatusSetting = null;
    try { StatusSetting = Vencord.Api.UserSettings.getUserSetting("status", "status") ?? null; } catch { }
    let CustomStatusSetting = null; // your custom status: { text, emojiId ("0": none), emojiName, expiresAtMs, ... }
    try { CustomStatusSetting = Vencord.Api.UserSettings.getUserSetting("status", "customStatus") ?? null; } catch { }
    // Discord's markdown parser, with the options its own message list uses.
    const Markdown = find("parseToAST");
    let liveUpdatesOk = true; // set false below if subscribing to Discord's events fails
    const MD_OPTIONS = { allowLinks: true, allowHeading: true, allowList: true, allowEmojiLinks: true };
    const CHAT_INTENTION = 3; // EmojiIntention.CHAT
    const STATUS_INTENTION = 1; // EmojiIntention.STATUS

    const TEXT_TYPES = new Set([0, 5]); // GUILD_TEXT, GUILD_ANNOUNCEMENT
    const VOICE_TYPES = new Set([2, 13]); // GUILD_VOICE, GUILD_STAGE_VOICE
    const FORUM_TYPES = new Set([15, 16]); // GUILD_FORUM, GUILD_MEDIA: posts instead of messages
    // How older (archived) forum posts are asked for: newest activity first, no tag filter, like Discord.
    const POST_SORT = 0, NO_TAGS = new Set(), TAG_SETTING = "match_some";
    const DM = 1, GROUP_DM = 3;
    const DISCORD_EPOCH = 1420070400000;
    // Tunables for this side (the Python settings live in config.py).
    const ICON_SIZE = 64; // avatar / server icon resolution requested from Discord's CDN
    const FETCH_LIMIT = 50; // messages fetched when a chat isn't loaded yet
    const PREVIEW_MAX_CHARS = 140;
    const FRECENT_EMOJI = 32; // "Frequently used" emoji shown in the picker
    const SUGGESTIONS = 8; // "@" / "#" suggestions shown above the reply box
    const CHANGE_BATCH_MS = 50; // changed chats are reported to the overlay at most this often
    const LISTS_BATCH_MS = 250; // a burst of list changes (e.g. many friends' statuses) is reported once

    // Last-message previews per channel, from messages Vesktop already has (opened chats, and messages that
    // arrive while it runs). Never fetched on purpose: the overlay makes no requests you didn't ask for.
    // Lives on window so it survives bridge.js reloads.
    const previews = (window.__vesktopOverlayPreviews ??= new Map());

    const userName = (u, guildId) =>
        (guildId && C.GuildMemberStore.getNick(guildId, u.id)) || u.globalName || u.username;

    const absolute = url => (url && url.startsWith("/") ? "https://discord.com" + url : url ?? null);

    // Snowflakes are numeric strings; compare without BigInt overhead.
    const cmpSnowflake = (a, b) =>
        (a?.length ?? 0) - (b?.length ?? 0) || ((a ?? "") < (b ?? "") ? -1 : (a ?? "") > (b ?? "") ? 1 : 0);
    const snowflakeTime = id => (id ? Number(BigInt(id) >> 22n) + DISCORD_EPOCH : 0);

    function channelName(ch) {
        if (ch.type === DM) {
            const u = C.UserStore.getUser(ch.recipients?.[0]);
            return u ? userName(u) : "Unknown user";
        }
        if (ch.type === GROUP_DM) {
            if (ch.name) return ch.name;
            return ch.recipients.map(id => C.UserStore.getUser(id)).filter(Boolean).map(u => userName(u)).join(", ");
        }
        return ch.name;
    }

    function channelIcon(ch) {
        if (ch.type === DM) {
            const u = C.UserStore.getUser(ch.recipients?.[0]);
            return absolute(u?.getAvatarURL(undefined, ICON_SIZE, false));
        }
        if (ch.type === GROUP_DM) {
            try { return absolute(C.IconUtils.getChannelIconURL({ id: ch.id, icon: ch.icon, size: ICON_SIZE })); }
            catch { return null; }
        }
        const g = C.GuildStore.getGuild(ch.guild_id);
        return g ? guildIcon(g) : null;
    }

    const guildIcon = g =>
        g.icon ? absolute(C.IconUtils.getGuildIconURL({ id: g.id, icon: g.icon, canAnimate: false, size: ICON_SIZE })) : null;

    const channelMuted = ch =>
        !!ch.guild_id && (C.UserGuildSettingsStore.isMuted(ch.guild_id)
            || C.UserGuildSettingsStore.isChannelMuted(ch.guild_id, ch.id));

    // Turn raw message markup (<@id>, <#id>, <:emoji:id>) into readable text.
    function cleanContent(text, guildId) {
        return text
            .replace(/<@!?(\d+)>/g, (m, id) => {
                const u = C.UserStore.getUser(id);
                return u ? "@" + userName(u, guildId) : "@user";
            })
            .replace(/<@&(\d+)>/g, (m, id) => {
                const r = guildId && C.GuildRoleStore.getRole?.(guildId, id);
                return r ? "@" + r.name : "@role";
            })
            .replace(/<#(\d+)>/g, (m, id) => {
                const c = C.ChannelStore.getChannel(id);
                return c ? "#" + c.name : m;
            })
            .replace(/<a?(:\w+:)\d+>/g, "$1")
            .replace(/<t:(\d+)(?::\w)?>/g, (m, s) => new Date(+s * 1000).toLocaleString());
    }

    // Discord's parse tree trimmed to what the overlay draws (see vesktop_discord_overlay/markdown.py for the node types).
    function simplifyAst(nodes) {
        const out = [];
        for (const n of Array.isArray(nodes) ? nodes : [nodes]) {
            if (n == null) continue;
            if (typeof n === "string") { out.push({ t: "text", v: n }); continue; }
            const kids = () => simplifyAst(n.content ?? []);
            switch (n.type) {
                case "text": out.push({ t: "text", v: String(n.content ?? "") }); break;
                case "br": case "newline": out.push({ t: "text", v: "\n" }); break;
                case "strong": case "em": case "u": case "s": case "spoiler": case "blockQuote": case "subtext":
                    out.push({ t: n.type, c: kids() }); break;
                case "heading": out.push({ t: "heading", level: n.level ?? 1, c: kids() }); break;
                case "inlineCode":
                    out.push({ t: "inlineCode", v: typeof n.content === "string" ? n.content : astText(n.content) }); break;
                case "codeBlock": out.push({ t: "codeBlock", lang: n.lang ?? "", v: n.content ?? "" }); break;
                case "link": case "url": case "autolink":
                    out.push({ t: "link", href: n.target ?? astText(n.content), c: kids() }); break;
                case "list":
                    out.push({ t: "list", ordered: !!n.ordered, start: n.start ?? 1, items: (n.items ?? []).map(simplifyAst) });
                    break;
                case "mention":
                    out.push({ t: "mention", v: astText(n.content) || "@unknown", me: !!n.userId && n.userId === myId() });
                    break;
                case "channelMention": out.push({ t: "mention", v: "#" + astText(n.content) }); break;
                case "emoji": out.push({ t: "emoji", v: n.surrogate ?? n.name ?? "" }); break;
                case "customEmoji":
                    out.push({ t: "customEmoji", name: (n.name ?? "").replace(/:/g, ""), id: n.emojiId, animated: !!n.animated });
                    break;
                case "timestamp": out.push({ t: "timestamp", v: n.formatted ?? n.full ?? "" }); break;
                default: // paragraphs and other wrappers: keep what's inside
                    if (Array.isArray(n.content)) out.push(...kids());
                    else if (typeof n.content === "string") out.push({ t: "text", v: n.content });
            }
        }
        return out;
    }

    const astText = nodes => simplifyAst(nodes ?? []).map(x => x.v ?? astText(x.c)).join("");
    const myId = () => C.UserStore.getCurrentUser()?.id;

    function messageAst(content, channelId) {
        if (!content) return [];
        try { return simplifyAst(Markdown.parseToAST(content, true, { ...MD_OPTIONS, channelId })); }
        catch { return [{ t: "text", v: content }]; }
    }

    // A forwarded message (Discord shows "↱ Forwarded" and the original): its text, images and files.
    function forwardedMessage(m, ch) {
        const snap = (m.messageSnapshots ?? m.message_snapshots ?? [])[0]?.message;
        if (!snap) return null;
        const media = messageMedia(snap);
        return { content: cleanContent(snap.content ?? "", ch.guild_id), ast: messageAst(snap.content ?? "", ch.id),
                 media, extras: remainingExtras(snap, media) };
    }

    // A poll: the question, each answer with its votes (and whether one is yours), and whether it has closed.
    function pollOf(m) {
        const p = m.poll;
        if (!p) return null;
        const counts = field(p.results ?? {}, "answerCounts", "answer_counts") ?? [];
        const answers = (p.answers ?? []).map(a => {
            const id = field(a, "answerId", "answer_id");
            const media = field(a, "pollMedia", "poll_media") ?? {};
            const c = counts.find(x => x.id === id) ?? {};
            const emoji = media.emoji?.name ? (media.emoji.id ? `:${media.emoji.name}:` : media.emoji.name) : "";
            return { text: media.text ?? "", emoji, count: c.count ?? 0, me: !!field(c, "meVoted", "me_voted") };
        });
        const expiry = p.expiry ? +new Date(+p.expiry || p.expiry) : null;
        const closed = !!field(p.results ?? {}, "isFinalized", "is_finalized") || (!!expiry && expiry < Date.now());
        return { question: p.question?.text ?? "", answers, total: answers.reduce((n, a) => n + a.count, 0), closed,
                 expiry };
    }

    // A bot's reply to a slash command: who used which command (Discord shows "Name used /command" above it).
    function commandOf(m, ch) {
        const meta = m.interaction ?? m.interactionMetadata ?? m.interaction_metadata;
        const name = meta?.name ?? meta?.displayName;
        if (!name) return null;
        const u = meta.user && (C.UserStore.getUser(meta.user.id) ?? meta.user);
        return { user: u ? (u.getAvatarURL ? userName(u, ch.guild_id) : u.global_name || u.username) : "Someone",
                 name: name.replace(/^\//, "") };
    }

    // Discord's "system messages" (calls, pins, people joining, ...) have no text of their own: Discord writes
    // the sentence from the message type. Returns { icon, text } (worded like Discord), or null for normal ones.
    const NORMAL_TYPES = new Set([0, 19, 20, 23]); // default, reply, slash command, app command
    function systemMessage(m, ch, author) {
        if (NORMAL_TYPES.has(m.type ?? 0)) return null;
        const person = x => {
            const id = x?.id ?? x;
            const u = C.UserStore.getUser(id);
            return u ? userName(u, ch?.guild_id) : (x?.global_name || x?.username || "someone");
        };
        const target = (m.mentions ?? [])[0];
        const guild = ch?.guild_id ? C.GuildStore.getGuild(ch.guild_id)?.name ?? "The server" : "The server";
        switch (m.type) {
            case 1: return { icon: "→", text: `${author} added ${person(target)} to the group.` };
            case 2: return (target?.id ?? target) === m.author.id
                ? { icon: "←", text: `${author} left the group.` }
                : { icon: "←", text: `${author} removed ${person(target)} from the group.` };
            case 3: {
                const call = m.call ?? {};
                const ended = call.endedTimestamp ?? call.ended_timestamp;
                if (!ended) return { icon: "📞", text: `${author} started a call.` };
                const ms = Math.max(0, +new Date(+ended || ended) - +new Date(+m.timestamp || m.timestamp));
                const lasted = ms < 60_000 ? "a few seconds" : ms < 120_000 ? "a minute"
                    : ms < 3_600_000 ? `${Math.round(ms / 60_000)} minutes`
                    : ms < 7_200_000 ? "an hour" : `${Math.round(ms / 3_600_000)} hours`;
                const joined = (call.participants ?? []).some(x => (x?.id ?? x) === myId());
                return joined || m.author.id === myId()
                    ? { icon: "📞", text: `${author} started a call that lasted ${lasted}.` }
                    : { icon: "📞", text: `You missed a call from ${author} that lasted ${lasted}.` };
            }
            case 4: return { icon: "✏", text: `${author} changed the channel name: ${m.content}` };
            case 5: return { icon: "✏", text: `${author} changed the channel icon.` };
            case 6: return { icon: "📌", text: `${author} pinned a message to this channel.` };
            case 7: return { icon: "→", text: `${author} joined the server.` };
            case 8: return { icon: "🚀", text: `${author} just boosted the server!` };
            case 9: case 10: case 11:
                return { icon: "🚀", text: `${author} just boosted the server! ${guild} has achieved Level ${m.type - 8}!` };
            case 12: return { icon: "→", text: `${author} has added ${m.content} to this channel.` };
            case 18: return { icon: "🧵", text: `${author} started a thread: ${m.content}` };
            case 14: return { icon: "⚠", text: "This server has been removed from Server Discovery." };
            case 15: return { icon: "✓", text: "This server is eligible for Server Discovery again." };
            case 16: case 17: return { icon: "⚠", text: "This server has failed Server Discovery activity requirements." };
            case 21: {
                const ref = m.messageReference ?? m.message_reference;
                const start = ref && (C.MessageStore.getMessage(ref.channel_id, ref.message_id) ?? m.referenced_message);
                const said = start ? cleanContent(start.content ?? "", ch?.guild_id).replace(/\s+/g, " ").trim() : "";
                return { icon: "🧵", text: said ? `This thread started from: "${said.slice(0, PREVIEW_MAX_CHARS)}"`
                                               : "This thread started from a message in the channel." };
            }
            case 22: return { icon: "👋", text: "Invite your friends to this server!" };
            case 24: return { icon: "🛡", text: `AutoMod has blocked a message from ${author}.` };
            case 25: return { icon: "⭐", text: `${author} subscribed to the server.` };
            case 27: return { icon: "🎙", text: `${author} started ${m.content || "a Stage"}.` };
            case 28: return { icon: "🎙", text: `${author} ended ${m.content || "the Stage"}.` };
            case 29: return { icon: "🎙", text: `${author} is now a speaker.` };
            case 31: return { icon: "🎙", text: `${author} changed the Stage topic: ${m.content}` };
            case 36: return { icon: "🛡", text: `${author} turned on security actions.` };
            case 37: return { icon: "🛡", text: `${author} turned off security actions.` };
            case 38: return { icon: "🛡", text: `${author} reported a raid.` };
            case 39: return { icon: "🛡", text: `${author} reported a false alarm.` };
            case 46: {
                const fields = {};
                for (const f of m.embeds?.[0]?.fields ?? []) fields[f.rawName ?? f.name] = f.rawValue ?? f.value;
                const q = fields.poll_question_text, won = fields.victor_answer_text;
                return { icon: "📊", text: `${author}'s poll${q ? ` "${q}"` : ""} has closed` +
                                           (won ? `: "${won}" won.` : ".") };
            }
            default: return m.content ? null : { icon: "•", text: `${author} did something Discord shows specially.` };
        }
    }

    // One message for the overlay. Works for both Discord's cached message records and raw API messages
    // (older history), which name a few fields differently.
    function formatMessage(m, ch) {
        const me = myId();
        const user = C.UserStore.getUser(m.author.id);
        const name = (author, u) => (u ? userName(u, ch.guild_id) : author.global_name || author.globalName || author.username);
        const ref = m.messageReference ?? m.message_reference;
        const isForward = ref?.type === 1; // a forward also points at its original, but isn't a reply
        const refMsg = ref && !isForward
            && (C.MessageStore.getMessage(ref.channel_id, ref.message_id) ?? m.referenced_message);
        const media = messageMedia(m);
        const gifOnly = isGifLinkOnly(m);
        const author = name(m.author, user);
        return {
            id: m.id,
            authorId: m.author.id,
            author,
            system: systemMessage(m, ch, author),
            forwarded: forwardedMessage(m, ch),
            poll: pollOf(m),
            command: commandOf(m, ch),
            avatar: user ? absolute(user.getAvatarURL(ch.guild_id, ICON_SIZE, false)) : rawAvatar(m.author),
            self: m.author.id === me,
            time: typeof m.timestamp === "string" ? Date.parse(m.timestamp) : +m.timestamp,
            content: gifOnly ? "" : cleanContent(m.content ?? "", ch.guild_id),
            ast: gifOnly ? [] : messageAst(m.content, ch.id),
            mentionsMe: m.mentioned ?? (!!m.mention_everyone || (m.mentions ?? []).some(u => u.id === me)),
            edited: !!(m.editedTimestamp ?? m.edited_timestamp),
            reactions: (m.reactions ?? []).map(r => ({
                count: r.count ?? 0,
                me: !!(r.me || r.me_burst),
                emoji: r.emoji?.id
                    ? { id: r.emoji.id, name: r.emoji.name, animated: !!r.emoji.animated }
                    : { char: r.emoji?.name ?? "?", name: emojiName(r.emoji?.name) },
            })),
            media,
            extras: remainingExtras(m, media),
            reply: refMsg ? {
                id: ref.message_id,
                author: name(refMsg.author, C.UserStore.getUser(refMsg.author.id)),
                text: (cleanContent(refMsg.content ?? "", ch.guild_id).replace(/\s+/g, " ").trim()
                    || systemMessage(refMsg, ch, "")?.text.trim()
                    || messageExtras(refMsg).join(" ") || "…").slice(0, PREVIEW_MAX_CHARS),
            } : null,
        };
    }

    // ":thumbsup:" for 👍 (for tooltips); null if Discord doesn't know it.
    function emojiName(char) {
        try { return EmojiData.convertSurrogateToName(char, false) || null; } catch { return null; }
    }

    // A message from Discord's cache, or fetched if it isn't there (e.g. older history loaded by scrolling).
    async function getMessage(channelId, messageId) {
        const cached = C.MessageStore.getMessage(channelId, messageId);
        if (cached) return cached;
        const res = await C.RestAPI.get({ url: `/channels/${channelId}/messages`, query: { around: messageId, limit: 1 } });
        return (res.body ?? []).find(m => m.id === messageId) ?? null;
    }

    function rawAvatar(author) {
        if (author.avatar) return `https://cdn.discordapp.com/avatars/${author.id}/${author.avatar}.webp?size=${ICON_SIZE}`;
        return `https://cdn.discordapp.com/embed/avatars/${Number(BigInt(author.id) >> 22n) % 6}.png`;
    }

    // Text ready to send: Discord's parser turns :name: into emoji; emoji you can't use here (another
    // server's without Nitro) go back to plain :name: text, as Discord's own client won't send them.
    function parseForSend(ch, content) {
        const parsed = Parser.parse(ch, content);
        let text = parsed.content;
        for (const e of parsed.invalidEmojis) {
            text = text.replaceAll(`<${e.animated ? "a" : ""}:${e.name}:${e.id}>`, `:${e.name}:`);
        }
        return { content: text, invalidEmojis: parsed.invalidEmojis, validNonShortcutEmojis: parsed.validNonShortcutEmojis };
    }

    function replyOptions(ch, replyToId) {
        return {
            messageReference: { guild_id: ch.guild_id ?? undefined, channel_id: ch.id, message_id: replyToId },
            allowedMentions: { parse: ["users", "roles", "everyone"], replied_user: true },
        };
    }

    let CloudUploadClass;
    const cloudUpload = () => (CloudUploadClass ??= W.find(m => m?.prototype?.trackUploadFinished));

    // Works for both store message records and raw REST/gateway message objects.
    function messageExtras(m) {
        const extras = [];
        const forwarded = (m.messageSnapshots ?? m.message_snapshots ?? [])[0]?.message;
        if (forwarded) extras.push(`↱ ${(forwarded.content ?? "").replace(/\s+/g, " ").trim() || "Forwarded message"}`);
        if (m.poll) extras.push(`📊 ${m.poll.question?.text ?? "Poll"}`);
        for (const a of m.attachments ?? []) extras.push(attachmentLabel(a));
        for (const s of m.stickerItems ?? m.sticker_items ?? []) extras.push(`[sticker: ${s.name}]`);
        if (!m.content && m.embeds?.length) extras.push(`[embed${m.embeds[0].title ? ": " + m.embeds[0].title : ""}]`);
        return extras;
    }

    const field = (obj, camel, snake) => obj?.[camel] ?? obj?.[snake];
    const isSpoiler = a => !!a.spoiler || (a.filename ?? "").startsWith("SPOILER_");

    // Images, GIFs and video thumbnails to draw inline. Each item:
    // kind: "image" (static), "anim" (animated .gif), "video" (looping silent mp4 like Klipy/Tenor GIFs),
    //       "poster" (thumbnail that opens in the browser); src/poster: what to load; full: what a click opens.
    function messageMedia(m) {
        const out = [];
        for (const a of m.attachments ?? []) {
            const type = field(a, "contentType", "content_type") ?? "";
            const proxy = field(a, "proxyURL", "proxy_url") ?? a.url;
            if (!a.width || !a.height) continue;
            if (type.startsWith("image/")) {
                out.push({ kind: type === "image/gif" ? "anim" : "image", src: proxy, full: a.url,
                           w: a.width, h: a.height, spoiler: isSpoiler(a) });
            } else if (type.startsWith("video/")) {
                const poster = proxy + (proxy.includes("?") ? "&" : "?") + "format=jpeg";
                out.push({ kind: "poster", src: poster, full: a.url, w: a.width, h: a.height, spoiler: isSpoiler(a) });
            }
        }
        for (const e of m.embeds ?? []) {
            const thumb = e.thumbnail, image = e.image, video = e.video;
            const src = x => field(x, "proxyURL", "proxy_url") ?? x?.url;
            if (e.type === "gifv" && video) {
                out.push({ kind: "video", src: src(video), poster: thumb ? src(thumb) : null, full: e.url ?? video.url,
                           w: video.width ?? thumb?.width, h: video.height ?? thumb?.height });
            } else if (e.type === "image" && (image || thumb)) {
                const i = image ?? thumb;
                out.push({ kind: /\.gif(\?|$)/i.test(i.url ?? "") ? "anim" : "image", src: src(i), full: e.url ?? i.url,
                           w: i.width, h: i.height });
            } else if (e.type === "video" && thumb) {
                out.push({ kind: "poster", src: src(thumb), full: e.url, w: thumb.width, h: thumb.height,
                           youtube: youtubeId(e.url) ?? youtubeId(video?.url) });
            } else if (image) {
                out.push({ kind: "image", src: src(image), full: image.url, w: image.width, h: image.height });
            }
        }
        for (const st of m.stickerItems ?? m.sticker_items ?? []) {
            const fmt = field(st, "formatType", "format_type");
            if (fmt === 3) continue; // Lottie stickers aren't images; left as text
            const url = `https://media.discordapp.net/stickers/${st.id}.${fmt === 4 ? "gif" : "png"}?size=160`;
            out.push({ kind: fmt === 4 ? "anim" : "image", src: url, full: url, w: 160, h: 160, sticker: true });
        }
        return out.filter(x => x.src && x.w && x.h);
    }

    // The 11-character id from any YouTube link form: watch?v=, youtu.be/, shorts/, embed/, live/.
    function youtubeId(url) {
        const m = /(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|embed\/|live\/)|youtu\.be\/)([\w-]{11})/.exec(url ?? "");
        return m ? m[1] : null;
    }

    // Extras for things not drawn inline (other files, Lottie stickers, text-only embeds).
    // "🎤 Voice message · 0:12" for voice messages (they come with a waveform), "🎵 name · 0:12" for other
    // audio, "[attachment: name]" for other files. (Videos have a duration too, but are drawn as thumbnails.)
    function attachmentLabel(a) {
        const secs = field(a, "durationSecs", "duration_secs");
        const length = secs == null ? "" : ` · ${Math.floor(Math.round(secs) / 60)}:${String(Math.round(secs) % 60).padStart(2, "0")}`;
        if (a.waveform != null) return `🎤 Voice message${length}`;
        if ((field(a, "contentType", "content_type") ?? "").startsWith("audio/")) return `🎵 ${a.filename}${length}`;
        return `[attachment: ${a.filename}]`;
    }

    function remainingExtras(m, media) {
        const extras = [];
        for (const a of m.attachments ?? []) {
            const type = field(a, "contentType", "content_type") ?? "";
            if (!(a.width && a.height && (type.startsWith("image/") || type.startsWith("video/")))) {
                extras.push(attachmentLabel(a));
            }
        }
        for (const st of m.stickerItems ?? m.sticker_items ?? []) {
            if (field(st, "formatType", "format_type") === 3) extras.push(`[sticker: ${st.name}]`);
        }
        if (!m.content && !media.length && m.embeds?.length) {
            extras.push(`[embed${m.embeds[0].title ? ": " + m.embeds[0].title : ""}]`);
        }
        return extras;
    }

    // Discord hides the message text when it's nothing but the link of a GIF embed; do the same.
    const isGifLinkOnly = m =>
        !!m.content && (m.embeds ?? []).some(e => e.type === "gifv" && e.url === m.content.trim());

    function rememberPreview(channelId, m) {
        if (!m?.id || !m.author) return;
        const old = previews.get(channelId);
        if (old && cmpSnowflake(old.id, m.id) > 0) return;
        const ch = C.ChannelStore.getChannel(channelId);
        const author = C.UserStore.getUser(m.author.id) ?? m.author;
        const system = systemMessage(m, ch, userName(author, ch?.guild_id));
        const text = system ? `${system.icon} ${system.text}`
            : (isGifLinkOnly(m) ? "GIF" : cleanContent(m.content ?? "", ch?.guild_id).replace(/\s+/g, " ").trim())
              || messageExtras(m).join(" ") || "…";
        previews.set(channelId, {
            id: m.id,
            author: userName(author, ch?.guild_id),
            self: m.author.id === C.UserStore.getCurrentUser().id,
            system: !!system, // the text already says who
            text: text.slice(0, PREVIEW_MAX_CHARS),
        });
    }

    function previewFor(ch) {
        // Prefer what's already loaded in Discord's message cache.
        const loaded = C.MessageStore.getMessages(ch.id)?.last?.();
        if (loaded) rememberPreview(ch.id, loaded);
        return previews.get(ch.id) ?? null;
    }


    // Tell the overlay which chats just changed (a message arrived, was edited or deleted, or got a
    // reaction), so it can re-read the open one at once instead of waiting for its next poll. Changes are
    // batched briefly, and sent after Discord's stores have applied them.
    const changedChats = new Set();
    let changedTimer = null;
    function chatChanged(channelId) {
        if (!channelId) return;
        changedChats.add(channelId);
        changedTimer ??= setTimeout(() => {
            changedTimer = null;
            const channels = [...changedChats];
            changedChats.clear();
            window.__vesktopOverlayEvent?.(JSON.stringify({ type: "chats", channels }));
        }, CHANGE_BATCH_MS);
    }
    const CHAT_EVENTS = {
        MESSAGE_CREATE: e => {
            if (e.optimistic) return; // our own message before Discord confirms it; the real one follows
            if (e.message) rememberPreview(e.channelId, e.message); // keep list previews live too
            return e.channelId;
        },
        MESSAGE_UPDATE: e => e.message?.channel_id,
        MESSAGE_DELETE: e => e.channelId,
        MESSAGE_DELETE_BULK: e => e.channelId,
        MESSAGE_REACTION_ADD: e => e.channelId,
        MESSAGE_REACTION_REMOVE: e => e.channelId,
        MESSAGE_REACTION_REMOVE_ALL: e => e.channelId,
        MESSAGE_REACTION_REMOVE_EMOJI: e => e.channelId,
        MESSAGE_POLL_VOTE_ADD: e => e.channelId ?? e.channel_id, // poll votes come as their own events
        MESSAGE_POLL_VOTE_REMOVE: e => e.channelId ?? e.channel_id,
    };
    window.__vesktopOverlayUnsub?.();
    const chatHandlers = Object.entries(CHAT_EVENTS).map(([type, channelOf]) => [type, e => chatChanged(channelOf(e))]);
    try {
        for (const [type, handler] of chatHandlers) C.FluxDispatcher.subscribe(type, handler);
        window.__vesktopOverlayUnsub = () => {
            for (const [type, handler] of chatHandlers) C.FluxDispatcher.unsubscribe(type, handler);
        };
    } catch { liveUpdatesOk = false; } // the overlay still polls, just less promptly

    // Push "who's typing where" to the overlay as soon as it changes (window.__vesktopOverlayEvent is a
    // DevTools binding added by bridge.py). TypingStore also expires typists on its own; its change
    // listener catches that too.
    // Start by watching every DM, so a friend who was already typing when we connected is still tracked.
    const typingChannels = new Set();
    try { C.PrivateChannelSortStore.getPrivateChannelIds().forEach(id => typingChannels.add(id)); } catch { }
    let lastTyping = "";
    function typingNow() {
        const me = myId(), out = {};
        for (const id of [...typingChannels]) {
            const ch = C.ChannelStore.getChannel(id);
            const users = Object.keys(C.TypingStore.getTypingUsers(id) ?? {}).filter(u => u !== me);
            if (!users.length) { typingChannels.delete(id); continue; }
            out[id] = users.map(u => C.UserStore.getUser(u)).filter(Boolean).map(u => userName(u, ch?.guild_id));
        }
        return out;
    }
    function pushTyping() {
        const json = JSON.stringify({ type: "typing", channels: typingNow() });
        if (json === lastTyping) return;
        lastTyping = json;
        window.__vesktopOverlayEvent?.(json);
    }
    const onTypingStart = e => { typingChannels.add(e.channelId); };
    window.__vesktopOverlayTypingUnsub?.();
    try {
        C.FluxDispatcher.subscribe("TYPING_START", onTypingStart);
        C.TypingStore.addChangeListener(pushTyping);
        window.__vesktopOverlayTypingUnsub = () => {
            C.FluxDispatcher.unsubscribe("TYPING_START", onTypingStart);
            C.TypingStore.removeChangeListener(pushTyping);
        };
    } catch { liveUpdatesOk = false; }

    // The sidebar's data changed (something read elsewhere, someone came online, a new DM, a server joined or
    // muted, ...): tell the overlay, so it re-reads the lists now instead of at its next safety-net check. All
    // of this is Discord data Vesktop already has in memory; nothing is asked of Discord's servers.
    let listsTimer = null;
    function listsChanged() {
        listsTimer ??= setTimeout(() => {
            listsTimer = null;
            window.__vesktopOverlayEvent?.(JSON.stringify({ type: "lists" }));
        }, LISTS_BATCH_MS);
    }
    const listStores = [C.ReadStateStore, C.PresenceStore, C.PrivateChannelSortStore, C.GuildStore,
        C.GuildReadStateStore, C.UserGuildSettingsStore, ActiveThreads, JoinedThreads, ArchivedThreads].filter(Boolean);
    window.__vesktopOverlayListsUnsub?.();
    try {
        for (const store of listStores) store.addChangeListener(listsChanged);
        window.__vesktopOverlayListsUnsub = () => listStores.forEach(store => store.removeChangeListener(listsChanged));
    } catch { liveUpdatesOk = false; }

    // Mute / deafen, the voice channel you're in, your status, and you (for the user panel).
    // What a friend is up to, as Discord shows it: their custom status if they set one ("🍕 brb dinner"),
    // otherwise their activity ("Playing Valorant", "Listening to Spotify"), otherwise null.
    const ACTIVITY_VERBS = { 0: "Playing", 1: "Streaming", 2: "Listening to", 3: "Watching", 5: "Competing in" };
    function activityText(userId) {
        const acts = C.PresenceStore.getActivities?.(userId) ?? [];
        const custom = acts.find(a => a.type === 4);
        if (custom && (custom.state || custom.emoji?.name)) {
            const emoji = custom.emoji && !custom.emoji.id ? custom.emoji.name : ""; // (server emoji: left out)
            const text = `${emoji} ${custom.state ?? ""}`.trim();
            if (text) return text;
        }
        const act = acts.find(a => a.type !== 4 && a.name);
        return act ? `${ACTIVITY_VERBS[act.type] ?? "Playing"} ${act.name}` : null;
    }

    // The people in your voice channel: who's speaking, who's muted or deafened.
    function voiceMembers(vc) {
        const states = Object.values(C.VoiceStateStore?.getVoiceStatesForChannel?.(vc.id) ?? {});
        return states.map(s => {
            const u = C.UserStore.getUser(s.userId);
            return {
                id: s.userId,
                name: u ? userName(u, vc.guild_id) : "Someone",
                avatar: u ? absolute(u.getAvatarURL(vc.guild_id, ICON_SIZE, false)) : null,
                speaking: !!Speaking?.isSpeaking?.(s.userId),
                mute: !!(s.selfMute || s.mute),
                deaf: !!(s.selfDeaf || s.deaf),
                me: s.userId === myId(),
            };
        }).sort((a, b) => a.name.localeCompare(b.name));
    }

    // Your custom status as the overlay shows it: { text, emoji: {char} | {id, name, url} | null, expires } or null.
    // (Discord clears an expired one itself, which arrives here like any other change.)
    function customStatus() {
        const s = CustomStatusSetting?.getSetting?.();
        if (!s || !(s.text || s.emojiName)) return null;
        const expires = Number(s.expiresAtMs ?? 0) || null;
        if (expires && expires <= Date.now()) return null;
        const custom = s.emojiId && s.emojiId !== "0";
        const emoji = !s.emojiName ? null : custom
            ? { id: s.emojiId, name: s.emojiName, url: `https://cdn.discordapp.com/emojis/${s.emojiId}.png?size=48` }
            : { char: s.emojiName, name: s.emojiName };
        return { text: s.text ?? "", emoji, expires };
    }

    function voiceState() {
        const vc = C.ChannelStore.getChannel(C.SelectedChannelStore.getVoiceChannelId());
        return {
            mute: C.MediaEngineStore.isSelfMute(),
            deaf: C.MediaEngineStore.isSelfDeaf(),
            channel: vc ? channelName(vc) : null,
            members: vc ? voiceMembers(vc) : [],
            status: StatusSetting?.getSetting() ?? null, // online | idle | dnd | invisible
            custom: customStatus(),
            me: (u => ({ name: userName(u), avatar: absolute(u.getAvatarURL(undefined, ICON_SIZE, false)) }))(
                C.UserStore.getCurrentUser()),
        };
    }

    // Push it the moment it changes, wherever it was changed (the overlay, Discord's own buttons, a keybind),
    // so the panel's buttons are never out of date.
    let lastVoice = "";
    function pushVoice() {
        let json;
        try { json = JSON.stringify({ type: "voice", ...voiceState() }); } catch { return; }
        if (json === lastVoice) return;
        lastVoice = json;
        window.__vesktopOverlayEvent?.(json);
    }
    const voiceStores = [C.MediaEngineStore, C.SelectedChannelStore, C.UserSettingsProtoStore, C.VoiceStateStore,
        Speaking].filter(store => store?.addChangeListener);
    // Someone joined, left, muted or started speaking in a voice channel of the server whose channels are open:
    // re-read the list. (Only that server is checked, so other servers' voice traffic costs nothing.)
    let watchedGuild = null, lastVoiceList = "";
    function voiceListChanged() {
        if (!watchedGuild) return;
        let sig;
        try { sig = JSON.stringify(guildVoiceChannels(watchedGuild).map(ch => [ch.id, voiceMembers(ch)])); } catch { return; }
        if (sig === lastVoiceList) return;
        lastVoiceList = sig;
        listsChanged();
    }
    const onVoiceChange = () => { pushVoice(); voiceListChanged(); };
    window.__vesktopOverlayVoiceUnsub?.();
    try {
        for (const store of voiceStores) store.addChangeListener(onVoiceChange);
        window.__vesktopOverlayVoiceUnsub = () => voiceStores.forEach(store => store.removeChangeListener(onVoiceChange));
    } catch { liveUpdatesOk = false; }

    function channelCard(ch, withPreview) {
        return {
            id: ch.id,
            name: channelName(ch),
            unread: C.ReadStateStore.hasUnread(ch.id),
            mentions: C.ReadStateStore.getMentionCount(ch.id),
            muted: channelMuted(ch),
            last: snowflakeTime(ch.lastMessageId),
            lastId: ch.lastMessageId ?? null,
            preview: withPreview ? previewFor(ch) : null,
        };
    }

    const guildTextChannels = gid =>
        (C.GuildChannelStore.getChannels(gid).SELECTABLE ?? []).map(x => x.channel).filter(c => TEXT_TYPES.has(c.type));
    // In the server's own order (Discord keeps them sorted).
    const guildVoiceChannels = gid =>
        (C.GuildChannelStore.getChannels(gid).VOCAL ?? []).map(x => x.channel).filter(c => VOICE_TYPES.has(c.type));

    // Frequently used emoji and the server emoji you may use (in this channel, or for a status), like Discord's picker.
    function usableEmoji(ch, intention) {
        const usable = e => {
            try { return EmojiUtils.getEmojiUnavailableReason({ emoji: e, channel: ch, intention }) == null; }
            catch { return false; }
        };
        const customEntry = e => ({
            id: e.id,
            name: e.name,
            animated: !!e.animated,
            url: `https://cdn.discordapp.com/emojis/${e.id}.png?size=48`,
        });
        const custom = [];
        for (const g of Object.values(C.GuildStore.getGuilds())) {
            const emojis = (C.EmojiStore.getGuildEmoji(g.id) ?? []).filter(e => e.available !== false && usable(e));
            if (emojis.length) custom.push({ guild: g.name, guildId: g.id, emojis: emojis.map(customEntry) });
        }
        // The open channel's server first, like Discord's picker.
        custom.sort((a, b) => (b.guildId === ch?.guild_id) - (a.guildId === ch?.guild_id));
        const frecent = (C.EmojiStore.emojiFrecencyWithoutFetchingLatest?.frequently ?? [])
            .filter(e => !e.id || usable(e))
            .slice(0, FRECENT_EMOJI)
            .map(e => (e.id ? customEntry(e) : { name: e.uniqueName ?? e.name, char: e.surrogates }));
        return { frecent, custom };
    }

    // Would Discord's sidebar list this channel (Browse Channels picks)? Previews stick to those.
    const shownInSidebar = (guildId, channelId) => !C.UserGuildSettingsStore.isOptInEnabled?.(guildId)
        || !!C.UserGuildSettingsStore.isChannelOrParentOptedIn?.(guildId, channelId);

    // A server's channel list as Discord's own sidebar draws it: your Browse Channels picks, hidden muted
    // channels and collapsed categories respected, in Discord's order. Category headings come as rows of their
    // own ({kind: "category"}); joined threads follow their channel ({kind: "thread"}).
    function sidebarRows(guildId) {
        const gc = ChannelList.getGuild(guildId).guildChannels;
        const out = [];
        const showable = id => shownInSidebar(guildId, id);
        gc.getSections().forEach((rows, section) => {
            let cat;
            try { cat = gc.getCategoryFromSection(section); } catch { return; } // (not a channel section)
            const name = cat?.record ? cat.record.name
                : section === gc.favoritesSectionNumber ? "Favorites" : null;
            // A collapsed category still shows its heading (so it can be opened) if it has channels for you.
            const collapsedWithChannels = cat?.record && cat.isCollapsed && Object.keys(cat.channels ?? {}).some(showable);
            if (name && (rows > 0 || collapsedWithChannels)) {
                out.push({ kind: "category", id: cat.record?.id ?? `section-${section}`, name, collapsed: !!cat.isCollapsed,
                           canCollapse: !!cat.record });
            }
            for (let r = 0; r < rows; r++) {
                let row;
                try { row = gc.getChannelFromSectionRow(section, r); } catch { continue; }
                const ch = row?.channel?.record;
                const card = ch && sidebarCard(ch);
                if (!card) continue;
                out.push(card);
                for (const id of row.channel.threadIds ?? []) {
                    const thread = C.ChannelStore.getChannel(id);
                    if (thread) out.push({ ...channelCard(thread, false), kind: "thread", parentId: ch.id });
                }
            }
        });
        return out;
    }

    function sidebarCard(ch) {
        if (TEXT_TYPES.has(ch.type)) return channelCard(ch, true);
        if (VOICE_TYPES.has(ch.type)) {
            const { limit, full } = voiceInfo(ch);
            return { ...channelCard(ch, false), voice: true, members: voiceMembers(ch), limit, full };
        }
        if (FORUM_TYPES.has(ch.type)) {
            const newPosts = JoinedThreads?.getNewThreadCount?.(ch.guild_id, ch.id) ?? 0;
            const card = channelCard(ch, false);
            return { ...card, forum: true, newPosts, unread: card.unread || newPosts > 0 };
        }
        return null; // (directories and such: not shown)
    }

    // A forum's posts, most recent activity first: the active ones Vesktop has, plus older ones loaded so far.
    const postsLoaded = (window.__vesktopOverlayPostsLoaded ??= new Set()); // forums whose older posts were asked for
    function forumPosts(forumId) {
        const forum = C.ChannelStore.getChannel(forumId);
        if (!forum) return { posts: [], more: false };
        const gid = forum.guild_id;
        const ids = new Set(Object.keys(ActiveThreads?.getThreadsForParent?.(gid, forumId) ?? {}));
        for (const id of ArchivedThreads?.getThreads?.(forumId, POST_SORT, NO_TAGS, TAG_SETTING) ?? []) ids.add(id);
        const posts = [...ids].map(id => C.ChannelStore.getChannel(id)).filter(Boolean)
            .sort((a, b) => cmpSnowflake(b.lastMessageId ?? b.id, a.lastMessageId ?? a.id))
            .map(t => {
                const starter = C.UserStore.getUser(t.ownerId);
                return {
                    ...channelCard(t, false),
                    kind: "post",
                    unread: !!C.ReadStateStore.isForumPostUnread?.(t.id),
                    isNew: !!C.ReadStateStore.isNewForumThread?.(t.id, forumId, gid),
                    newCount: PostUnreadCounts?.getCount?.(t.id) ?? null,
                    replies: Math.max(0, (t.messageCount ?? 1) - 1) || 0,
                    starter: starter ? userName(starter, gid) : null,
                    last: snowflakeTime(t.lastMessageId ?? t.id),
                };
            });
        const more = !postsLoaded.has(forumId)
            || !!ArchivedThreads?.getCanLoadMore?.(forumId, POST_SORT, NO_TAGS, TAG_SETTING);
        const loading = !!ArchivedThreads?.isLoading?.(forumId, POST_SORT, NO_TAGS, TAG_SETTING);
        return { posts, more, loading };
    }

    // Marking read as Discord does: a forum as seen up to now (its "N new" posts), anything else up to its
    // newest message; joined threads under it too.
    function readStatesFor(ch) {
        const out = [];
        if (FORUM_TYPES.has(ch.type)) {
            out.push({ channelId: ch.id, messageId: C.SnowflakeUtils.fromTimestamp(Date.now()), readStateType: 0 });
        } else if (C.ReadStateStore.hasUnread(ch.id)) {
            const messageId = C.ReadStateStore.lastMessageId?.(ch.id) ?? ch.lastMessageId;
            if (messageId) out.push({ channelId: ch.id, messageId, readStateType: 0 });
        }
        const threads = JoinedThreads?.getActiveJoinedThreadsForParent?.(ch.guild_id, ch.id) ?? {};
        for (const id of Object.keys(threads)) {
            const thread = C.ChannelStore.getChannel(id);
            if (thread && C.ReadStateStore.hasUnread(id)) {
                const messageId = C.ReadStateStore.lastMessageId?.(id) ?? thread.lastMessageId;
                if (messageId) out.push({ channelId: id, messageId, readStateType: 0 });
            }
        }
        return out;
    }

    // A voice channel's user limit (0: none) and whether it's full for you (moderators can still join).
    function voiceInfo(ch) {
        const limit = ch.type === 2 ? ch.userLimit ?? 0 : 0; // (stages count listeners differently)
        const count = Object.keys(C.VoiceStateStore?.getVoiceStatesForChannel?.(ch.id) ?? {}).length;
        const canBypass = C.PermissionStore?.can?.(C.PermissionsBits?.MOVE_MEMBERS, ch);
        return { id: ch.id, name: ch.name, limit, full: limit > 0 && count >= limit && !canBypass };
    }

    function headerFor(ch) {
        const guild = ch.guild_id ? C.GuildStore.getGuild(ch.guild_id) : null;
        const parent = ch.isThread?.() ? C.ChannelStore.getChannel(ch.parent_id) : null;
        const inForum = parent && FORUM_TYPES.has(parent.type);
        const mark = parent ? (inForum ? "" : "↳ ") : VOICE_TYPES.has(ch.type) ? "🔊 " : "#";
        return {
            id: ch.id,
            name: guild ? mark + ch.name : channelName(ch),
            place: guild ? (parent ? `${guild.name} › ${inForum ? "" : "#"}${parent.name}` : guild.name)
                : ch.type === GROUP_DM ? "Group DM" : "Direct Message",
            forum: inForum ? { id: parent.id, name: parent.name } : null, // a forum post: the forum it's in
            icon: channelIcon(ch),
            guildId: guild?.id ?? null,
            voice: VOICE_TYPES.has(ch.type) ? voiceInfo(ch) : null, // a voice channel's chat
        };
    }

    return {
        // Which features can't work because a Discord update renamed something they need ([] = all fine).
        health() {
            const needs = {
                "the chat list": [C.ChannelStore, C.PrivateChannelSortStore, C.GuildStore, C.GuildChannelStore,
                    C.ReadStateStore, C.UserGuildSettingsStore, C.PresenceStore, C.UserStore],
                "server channels as Discord shows them": [ChannelList],
                "forums and threads": [ActiveThreads, JoinedThreads, ArchivedThreads, ThreadActions, C.SnowflakeUtils],
                "messages": [C.MessageStore, C.MessageActions, C.RestAPI, Markdown],
                "sending messages": [Parser, U?.sendMessage],
                "emoji": [EmojiData, EmojiUtils, C.EmojiStore],
                "typing indicators": [Typing, C.TypingStore],
                "live updates": [C.FluxDispatcher, liveUpdatesOk || null],
                "mute and deafen": [Voice, C.MediaEngineStore],
                "joining and leaving voice": [VoiceChannels, C.SelectedChannelStore],
                "who's in voice channels": [C.VoiceStateStore],
                "your status": [StatusSetting],
                "your custom status": [CustomStatusSetting],
                "opening chats in Vesktop": [C.NavigationRouter, C.ChannelRouter],
            };
            return Object.entries(needs).filter(([, parts]) => parts.some(p => !p)).map(([feature]) => feature);
        },

        // DMs and group DMs, most recent first (Discord's own DM order).
        friends() {
            return C.PrivateChannelSortStore.getPrivateChannelIds()
                .map(id => C.ChannelStore.getChannel(id))
                .filter(Boolean)
                .map(ch => {
                    const recipient = ch.type === DM ? ch.recipients?.[0] : null;
                    return {
                        ...channelCard(ch, true),
                        icon: channelIcon(ch),
                        status: recipient ? C.PresenceStore.getStatus(recipient) : null,
                        activity: recipient ? activityText(recipient) : null,
                        typing: Object.keys(C.TypingStore.getTypingUsers(ch.id) ?? {}).some(u => u !== myId()),
                    };
                });
        },

        // Servers: unmuted first, then pings, then most recent activity.
        servers() {
            const out = [];
            for (const g of Object.values(C.GuildStore.getGuilds())) {
                const channels = guildTextChannels(g.id).filter(ch => shownInSidebar(g.id, ch.id));
                let latest = null;
                for (const ch of channels) {
                    if (!channelMuted(ch) && (!latest || cmpSnowflake(ch.lastMessageId, latest.lastMessageId) > 0)) latest = ch;
                }
                const preview = latest ? previewFor(latest) : null;
                out.push({
                    id: g.id,
                    name: g.name,
                    icon: guildIcon(g),
                    acronym: g.acronym,
                    unread: C.GuildReadStateStore.hasUnread(g.id),
                    mentions: C.GuildReadStateStore.getMentionCount(g.id),
                    muted: C.UserGuildSettingsStore.isMuted(g.id),
                    last: snowflakeTime(latest?.lastMessageId),
                    lastId: latest?.lastMessageId ?? null,
                    preview: preview && { ...preview, channel: latest.name },
                });
            }
            out.sort((a, b) => a.muted - b.muted || (b.mentions > 0) - (a.mentions > 0) || cmpSnowflake(b.lastId, a.lastId));
            return out;
        },

        // One server's channel list, as Discord's sidebar shows it (see sidebarRows). If a Discord update broke
        // that, every channel you can see instead, in the server's order (health() reports it).
        channels(guildId) {
            watchedGuild = guildId;
            let rows;
            try { rows = sidebarRows(guildId); } catch { rows = null; }
            if (!rows) {
                const all = C.GuildChannelStore.getChannels(guildId);
                return [...(all.SELECTABLE ?? []), ...(all.VOCAL ?? [])].map(x => sidebarCard(x.channel)).filter(Boolean);
            }
            // A heading with nothing under it (its channels are all kinds the overlay doesn't show): left out,
            // unless it's collapsed (then it's how you open it).
            return rows.filter((r, i) => r.kind !== "category" || r.collapsed
                || (rows[i + 1] && rows[i + 1].kind !== "category"));
        },

        // "@" suggestions in the reply box: people in this chat matching what's typed after the @ (names that
        // start with it first; then recent speakers here first), as {name, username, avatar, insert}. The
        // insert is "@username", which Discord's parser turns into a real mention when the message is sent.
        suggestPeople(channelId, query) {
            const ch = C.ChannelStore.getChannel(channelId);
            if (!ch) return [];
            const gid = ch.guild_id ?? null;
            const ids = [];
            const add = id => { if (id && !ids.includes(id)) ids.push(id); };
            (C.MessageStore.getMessages(channelId)?.toArray?.() ?? []).slice().reverse().forEach(m => add(m.author?.id));
            (ch.recipients ?? []).forEach(add);
            if (gid) (C.GuildMemberStore.getMemberIds?.(gid) ?? []).forEach(add);
            const q = query.toLowerCase();
            const people = [];
            for (const id of ids) {
                const u = C.UserStore.getUser(id);
                if (!u || id === myId()) continue;
                const name = userName(u, gid);
                const names = [name, u.username, u.globalName].filter(Boolean).map(n => n.toLowerCase());
                const rank = names.some(n => n.startsWith(q)) ? 0 : names.some(n => n.includes(q)) ? 1 : -1;
                if (rank < 0) continue;
                people.push({ rank, kind: "person", id, name, username: u.username, insert: "@" + u.username + " ",
                              avatar: absolute(u.getAvatarURL(gid ?? undefined, ICON_SIZE, false)) });
                if (people.length >= 60) break; // (plenty to pick the best few from)
            }
            people.sort((a, b) => a.rank - b.rank); // (stable: recent speakers stay first within a rank)
            const out = people.slice(0, SUGGESTIONS).map(({ rank, ...p }) => p);
            const canPingAll = gid && C.PermissionStore?.can?.(C.PermissionsBits?.MENTION_EVERYONE, ch);
            for (const special of canPingAll ? ["everyone", "here"] : []) {
                if (special.startsWith(q)) out.push({ kind: "special", id: special, name: "@" + special,
                                                      insert: "@" + special + " " });
            }
            return out.slice(0, SUGGESTIONS);
        },

        // "#" suggestions: this server's channels you can see, matching what's typed after the #, inserted as
        // "#name" (Discord's parser turns it into a channel link).
        suggestChannels(channelId, query) {
            const ch = C.ChannelStore.getChannel(channelId);
            if (!ch?.guild_id) return [];
            const all = C.GuildChannelStore.getChannels(ch.guild_id);
            const q = query.toLowerCase();
            const found = [...(all.SELECTABLE ?? []), ...(all.VOCAL ?? [])].map(x => x.channel)
                .map(c => ({ c, n: c.name.toLowerCase() }))
                .filter(({ n }) => n.includes(q))
                .sort((a, b) => b.n.startsWith(q) - a.n.startsWith(q));
            return found.slice(0, SUGGESTIONS).map(({ c }) => ({
                kind: "channel", id: c.id, name: c.name, insert: "#" + c.name + " ",
                icon: VOICE_TYPES.has(c.type) ? "voice" : FORUM_TYPES.has(c.type) ? "forum" : "text",
            }));
        },

        // A forum's posts (see forumPosts).
        posts(forumId) { return forumPosts(forumId); },

        // Load the next page of a forum's older posts from Discord (the overlay asks when you scroll to the end
        // of the list, as Discord's app does). They arrive as a list change.
        olderPosts(forumId) {
            const forum = C.ChannelStore.getChannel(forumId);
            if (!forum) return false;
            const offset = postsLoaded.has(forumId)
                ? ArchivedThreads.getNextOffset(forumId, POST_SORT, NO_TAGS, TAG_SETTING) : 0;
            postsLoaded.add(forumId);
            ThreadActions.loadArchivedThreads({ guildId: forum.guild_id, channelId: forumId, sortOrder: POST_SORT,
                                                tagFilter: NO_TAGS, tagSetting: TAG_SETTING, offset });
            return true;
        },

        // Collapse or expand a category, in Discord too (it's your Discord setting).
        collapseCategory(categoryId, collapsed) {
            C.FluxDispatcher.dispatch({ type: collapsed ? "CATEGORY_COLLAPSE" : "CATEGORY_EXPAND", id: categoryId });
            return true;
        },

        // Everything the sidebar needs in one round trip; channels only when a server is open, posts only when
        // one of its forums is.
        overview(guildId, forumId) {
            watchedGuild = guildId ?? null;
            return { friends: this.friends(), servers: this.servers(), channels: guildId ? this.channels(guildId) : null,
                     posts: forumId ? forumPosts(forumId) : null };
        },

        // Which conversation Vesktop currently shows, so the overlay can open on it.
        current() {
            const ch = C.ChannelStore.getChannel(C.SelectedChannelStore.getChannelId());
            return ch ? { id: ch.id, guildId: ch.guild_id ?? null } : null;
        },

        async messages(channelId, count = 30) {
            const ch = C.ChannelStore.getChannel(channelId);
            if (!ch) return { error: "Channel not found" };
            let store = C.MessageStore.getMessages(channelId);
            if (!store?.ready || store.length < count) {
                // No timer-based waiting here: Chromium throttles timers while Vesktop is hidden or in the
                // tray, which turned short waits into timeouts. If it isn't ready yet, the next poll catches up.
                await C.MessageActions.fetchMessages({ channelId, limit: FETCH_LIMIT });
                store = C.MessageStore.getMessages(channelId);
            }
            const me = C.UserStore.getCurrentUser().id;
            const msgs = (store?.toArray?.() ?? store?._array ?? []).slice(-count);
            const typing = Object.keys(C.TypingStore.getTypingUsers(channelId) ?? {})
                .filter(id => id !== me)
                .map(id => C.UserStore.getUser(id))
                .filter(Boolean)
                .map(u => userName(u, ch.guild_id));
            // The first unread message, for the "NEW" line (read before the overlay marks the chat read).
            const firstUnreadId = C.ReadStateStore.hasUnread(channelId)
                ? C.ReadStateStore.getOldestUnreadMessageId?.(channelId) ?? null : null;
            return { ...headerFor(ch), typing, firstUnreadId, messages: msgs.map(m => formatMessage(m, ch)) };
        },

        // Up to `limit` messages before `beforeId`, oldest first, fetched the same way Discord's client does.
        // Goes straight to the API instead of Discord's message cache, so the live (newest) view isn't disturbed.
        async olderMessages(channelId, beforeId, limit = 50) {
            const ch = C.ChannelStore.getChannel(channelId);
            if (!ch) return { error: "Channel not found" };
            const res = await C.RestAPI.get({ url: `/channels/${channelId}/messages`, query: { before: beforeId, limit } });
            const raw = res.body ?? [];
            return { messages: raw.slice().reverse().map(m => formatMessage(m, ch)), more: raw.length === limit };
        },

        // Runs Discord's own message parser first, so :skull: becomes 💀 and :custom: becomes <:custom:id>.
        // replyToId makes it a reply to that message (pinging its author, as Discord does by default).
        async send(channelId, content, replyToId = null) {
            const ch = C.ChannelStore.getChannel(channelId);
            const parsed = parseForSend(ch, content);
            await U.sendMessage(channelId, parsed, false, replyToId ? replyOptions(ch, replyToId) : {});
            return true;
        },

        // A pasted image (base64 PNG) with optional text, uploaded the way Discord's own uploads are
        // (CloudUpload, as Vencord's voice-message plugin does), then posted as a message.
        async sendImage(channelId, content, base64, filename, replyToId = null) {
            const CloudUpload = cloudUpload();
            if (!CloudUpload) throw new Error("Image upload isn't available in this Vesktop version");
            const ch = C.ChannelStore.getChannel(channelId);
            const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
            const file = new File([bytes], filename, { type: "image/png" });
            const upload = new CloudUpload({ file, isThumbnail: false, platform: 1 }, channelId, false, 0);
            await new Promise((resolve, reject) => {
                upload.on("complete", resolve);
                upload.on("error", () => reject(new Error("Image upload failed")));
                upload.upload();
            });
            const body = {
                channel_id: channelId,
                content: content ? parseForSend(ch, content).content : "",
                nonce: C.SnowflakeUtils.fromTimestamp(Date.now()),
                sticker_ids: [],
                type: 0,
                attachments: [{ id: "0", filename: upload.filename, uploaded_filename: upload.uploadedFilename }],
            };
            if (replyToId) {
                const { messageReference, allowedMentions } = replyOptions(ch, replyToId);
                body.message_reference = messageReference;
                body.allowed_mentions = allowedMentions;
            }
            await C.RestAPI.post({ url: C.Constants.Endpoints.MESSAGES(channelId), body });
            return true;
        },

        // All built-in emoji by category: { categories: [{ id, emojis: [{ name, char, names }] }] }.
        emojiCatalog() {
            return {
                categories: EmojiData.getCategories().map(id => ({
                    id,
                    emojis: (EmojiData.getByCategory(id) ?? []).map(e => ({
                        name: e.uniqueName,
                        char: e.surrogates,
                        names: e.names ?? e.emojiObject?.names ?? [e.uniqueName],
                    })),
                })),
            };
        },

        // Per-channel emoji: frequently used, plus the server emoji you're allowed to send in this channel.
        emojiForChannel(channelId) {
            return usableEmoji(C.ChannelStore.getChannel(channelId), CHAT_INTENTION);
        },

        // The same for your custom status: server emoji only if Discord lets you use them there (Nitro).
        emojiForStatus() {
            return usableEmoji(null, STATUS_INTENTION);
        },

        // GIF picker data. No query: Discord's trending categories. "__trending__": trending GIFs. Else: search.
        async gifs(query) {
            const base = { media_format: "mp4", locale: "en-US" };
            const item = g => ({ url: g.url, mp4: g.src, still: g.gif_src ?? g.preview, w: g.width, h: g.height, title: g.title ?? "" });
            if (!query) {
                const r = await C.RestAPI.get({ url: "/gifs/trending", query: base });
                const first = r.body.gifs?.[0];
                return {
                    categories: [
                        ...(first ? [{ name: "Trending GIFs", query: "__trending__", still: first.gif_src ?? first.src }] : []),
                        ...r.body.categories.map(c => ({ name: c.name, query: c.name, still: c.src })),
                    ],
                };
            }
            const r = query === "__trending__"
                ? await C.RestAPI.get({ url: "/gifs/trending-gifs", query: base })
                : await C.RestAPI.get({ url: "/gifs/search", query: { ...base, q: query } });
            return { gifs: (r.body ?? []).map(item) };
        },

        // Same calls Discord's own message box makes; Discord decides how often to tell the server.
        startTyping(channelId) { Typing.startTyping(channelId); return true; },
        stopTyping(channelId) { Typing.stopTyping(channelId); return true; },

        // Mark a chat read up to its newest message, as Discord's client does when you look at it
        // (the same event Vencord's "read all" plugin sends). Returns whether anything was unread.
        // Mark every unread channel of a server read (right-click a server). Returns how many.
        // Everything in a server you can see (picked in Browse Channels or not), forums and joined threads too.
        markServerRead(guildId) {
            const all = C.GuildChannelStore.getChannels(guildId);
            const channels = [...(all.SELECTABLE ?? []), ...(all.VOCAL ?? [])].map(x => x.channel);
            const readStates = channels.flatMap(readStatesFor);
            if (readStates.length) C.FluxDispatcher.dispatch({ type: "BULK_ACK", context: "APP", channels: readStates });
            return readStates.length;
        },

        markRead(channelId) {
            const ch = C.ChannelStore.getChannel(channelId);
            const readStates = ch ? readStatesFor(ch) : [];
            if (readStates.length) C.FluxDispatcher.dispatch({ type: "BULK_ACK", context: "APP", channels: readStates });
            return readStates.length > 0;
        },

        open(channelId) {
            // (A voice channel: shows it with its text chat open; Discord doesn't join it.)
            if (channelId) C.ChannelRouter.transitionToChannel(channelId, { openTextInVoiceIfVoiceChannel: true });
            return true;
        },

        // Open a server at the channel Discord would pick (its last viewed one).
        openServer(guildId) {
            const nav = C.NavigationRouter;
            if (nav.transitionToGuild) nav.transitionToGuild(guildId);
            else nav.transitionTo(`/channels/${guildId}`);
            return true;
        },

        // Open a chat scrolled to one message (right-click → Open in Vesktop).
        openMessage(channelId, messageId) {
            const ch = C.ChannelStore.getChannel(channelId);
            if (!ch) return false;
            C.NavigationRouter.transitionTo(`/channels/${ch.guild_id ?? "@me"}/${channelId}/${messageId}`);
            return true;
        },

        // Put the caret in the chat message box of whatever channel is showing.
        focusComposer() {
            const box = document.querySelector('[role="textbox"][data-slate-editor="true"]');
            box?.focus();
            return !!box;
        },

        voice() { return voiceState(); },

        // Leave the voice channel you're in.
        disconnectVoice() { VoiceChannels.disconnect(); return true; },
        joinVoice(channelId) { VoiceChannels.selectVoiceChannel(channelId); return true; }, // (switches calls)

        // Your status: "online", "idle", "dnd" or "invisible", as if set in Vesktop.
        setStatus(status) { StatusSetting.updateSetting(status); return true; },

        // Set your custom status ({ text, emoji: {char} | {id, name} | null, expires: ms or null }), or clear it (null).
        setCustomStatus(status) {
            CustomStatusSetting.updateSetting(status ? {
                text: status.text ?? "",
                emojiId: status.emoji?.id ?? "0",
                emojiName: status.emoji ? status.emoji.id ? status.emoji.name : status.emoji.char : "",
                expiresAtMs: String(status.expires ?? 0),
                createdAtMs: String(Date.now()),
            } : undefined); // (undefined: cleared, as Discord does)
            return customStatus();
        },

        // Add (add = true) or remove your reaction. emoji: { char } for built-in, { id, name } for server emoji.
        async react(channelId, messageId, emoji, add) {
            const key = encodeURIComponent(emoji.id ? `${emoji.name}:${emoji.id}` : emoji.char);
            const url = `/channels/${channelId}/messages/${messageId}/reactions/${key}/@me`;
            if (add) await C.RestAPI.put({ url, query: { location: "Message", type: 0 } });
            else await C.RestAPI.del({ url, query: { location: "Message", burst: false } });
            return true;
        },

        // One message, formatted like messages() does (to refresh it after you react to or edit it).
        async message(channelId, messageId) {
            const ch = C.ChannelStore.getChannel(channelId);
            const m = ch && await getMessage(channelId, messageId);
            return m ? formatMessage(m, ch) : null;
        },

        // A message's text ready to edit: mentions as @name / #channel and server emoji as :name:, which
        // Discord's parser turns back into real mentions and emoji when it's saved.
        async editText(channelId, messageId) {
            const ch = C.ChannelStore.getChannel(channelId);
            const m = ch && await getMessage(channelId, messageId);
            if (!m) return null;
            return (m.content ?? "")
                .replace(/<@!?(\d+)>/g, (s, id) => { const u = C.UserStore.getUser(id); return u ? "@" + u.username : s; })
                .replace(/<@&(\d+)>/g, (s, id) => {
                    const r = ch.guild_id && C.GuildRoleStore.getRole?.(ch.guild_id, id);
                    return r ? "@" + r.name : s;
                })
                .replace(/<#(\d+)>/g, (s, id) => { const c = C.ChannelStore.getChannel(id); return c?.name ? "#" + c.name : s; })
                .replace(/<a?:(\w+):\d+>/g, ":$1:");
        },

        async editMessage(channelId, messageId, content) {
            const ch = C.ChannelStore.getChannel(channelId);
            await C.MessageActions.editMessage(channelId, messageId, { content: parseForSend(ch, content).content });
            return true;
        },

        async deleteMessage(channelId, messageId) {
            await C.MessageActions.deleteMessage(channelId, messageId);
            return true;
        },

        toggleMute() { Voice.toggleSelfMute(); return this.voice(); },
        toggleDeaf() { Voice.toggleSelfDeaf(); return this.voice(); },
    };
})()
