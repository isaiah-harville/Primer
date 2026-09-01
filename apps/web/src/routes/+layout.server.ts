import { apiFor } from '$lib/server/api';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ request, fetch }) => {
	const api = apiFor(request, fetch);
	// Both are needed by the frame rather than by any one page: capabilities
	// so the interface hides what this deployment cannot do rather than
	// offering it and failing, and the libraries because the sidebar lists
	// them on every screen. Loading them here also means one request each per
	// navigation instead of one per page that happens to want them.
	const [capabilities, libraries] = await Promise.all([api.capabilities(), api.libraries()]);
	return { capabilities, libraries };
};
