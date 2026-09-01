import { apiFor } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ request, fetch }) => {
	// A conversation belongs to a library, so the first choice is which one.
	return { libraries: await apiFor(request, fetch).libraries() };
};
