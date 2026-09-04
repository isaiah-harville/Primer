import type { ConversationSummary } from '$lib/api/types';
import { apiFor } from '$lib/server/api';
import { chatFor } from '$lib/server/chat';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ request, fetch, depends }) => {
	// Named so the conversation list can be refreshed on its own.
	//
	// Answering a question adds a row to it, and the only way to say so used
	// to be `invalidateAll()` - which re-runs the chat page's load too, and
	// that load decides which conversation is on screen. So refreshing the
	// sidebar handed the transcript's fate to a round trip, and a load that
	// came back without the thread it had just written cleared the answer off
	// the screen. The sidebar is the only thing that needs to know, so it is
	// the only thing asked.
	depends('primer:conversations');
	// Same reasoning, for the sidebar's document counts: dropping a file into
	// a conversation should update a number in the frame, not re-decide what
	// the chat screen is showing.
	depends('primer:libraries');
	const api = apiFor(request, fetch);
	const [capabilities, libraries, principal] = await Promise.all([
		api.capabilities(),
		api.libraries(),
		api.me().catch(() => null),
	]);

	// Conversations belong to the frame rather than to the chat screen: the
	// sidebar lists them from wherever you are, the same way it lists
	// libraries. Asked for only when this deployment has a Chat to ask, and
	// an empty list rather than a broken page when it will not answer -
	// nothing here is worth failing a page load over.
	const conversations: ConversationSummary[] = capabilities.chat_available
		? await chatFor(request, fetch)
				.conversations()
				.catch(() => [])
		: [];

	return { capabilities, libraries, principal, conversations };
};
