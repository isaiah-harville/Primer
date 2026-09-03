import type { ConversationSummary, MessageSummary } from '$lib/api/types';
import { chatFor } from '$lib/server/chat';
import type { PageServerLoad } from './$types';

/** Matched before an id is put in a path, so nothing else can be. */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The chat screen: which models are offered, which conversations exist, and
 * the one being read, if any.
 *
 * The conversation is a search parameter rather than page state, so a thread
 * survives a refresh and can be linked to. Which one is open is exactly the
 * kind of thing a URL is for.
 *
 * A failure here is not a failure of the page: an empty list means no
 * history rather than a chat screen that will not load, and asking a new
 * question is the one thing this screen must always offer. Losing the model
 * list specifically is still worth saying out loud - `modelsUnavailable`
 * lets the page toast it - because an empty list here otherwise looks
 * exactly like a deployment that only offers its one default model.
 *
 * What is not swallowed is why a named conversation did not open. A thread
 * that silently appears blank looks like a thread that lost its messages, so
 * the reason is returned and said on the page.
 */
export const load: PageServerLoad = async ({ request, fetch, url }) => {
	const chat = chatFor(request, fetch);
	const asked = url.searchParams.get('conversation');
	const wanted = asked && UUID.test(asked) ? asked : null;

	const [modelsResult, conversations] = await Promise.all([
		chat
			.models()
			.then((body) => ({ models: body.models ?? [], unavailable: false }))
			.catch(() => ({ models: [] as { id: string; default: boolean }[], unavailable: true })),
		chat.conversations().catch((): ConversationSummary[] => []),
	]);
	const { models, unavailable: modelsUnavailable } = modelsResult;

	let opened: { conversation: ConversationSummary; messages: MessageSummary[] } | null = null;
	//: Why the conversation in the URL is not the one on screen: `missing` for
	//: one that is gone or was never this caller's, `unavailable` when Chat
	//: would not give up its messages.
	let unopened: 'missing' | 'unavailable' | null = null;

	if (wanted) {
		const conversation = conversations.find((candidate) => candidate.id === wanted);
		if (!conversation) {
			unopened = 'missing';
		} else {
			const messages = await chat.messages(wanted).catch((): MessageSummary[] | null => null);
			if (messages) opened = { conversation, messages };
			else unopened = 'unavailable';
		}
	}

	return { models, modelsUnavailable, conversations, opened, unopened };
};
