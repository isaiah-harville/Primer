import { apiFor } from '$lib/server/api';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ request, fetch }) => {
	const api = apiFor(request, fetch);
	const [capabilities, libraries, principal] = await Promise.all([
		api.capabilities(),
		api.libraries(),
		api.me().catch(() => null),
	]);
	return { capabilities, libraries, principal };
};
