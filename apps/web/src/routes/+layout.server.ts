import { apiFor } from '$lib/server/api';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ request, fetch }) => {
	// Loaded once for the whole app: the interface hides what this
	// deployment cannot do rather than offering it and failing.
	return { capabilities: await apiFor(request, fetch).capabilities() };
};
