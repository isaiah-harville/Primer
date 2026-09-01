<script lang="ts">
	import { TriangleAlert } from '@lucide/svelte';

	interface Props {
		authEnabled: boolean;
	}

	let { authEnabled }: Props = $props();
</script>

<!--
  Permanent, not dismissible. With authentication off every request is the
  same user, so anyone who can reach this page can read and delete every
  library in it. A banner someone dismissed on Monday would be doing nothing
  on Friday, which is exactly when it matters.

  It sits in the frame rather than above it. A strip across the top made the
  whole page taller than the window, so every screen scrolled slightly
  whether or not it had anything to scroll.
-->
{#if !authEnabled}
	<div
		class="rounded-md border border-warning/40 bg-warning/10 px-2.5 py-2 text-xs
			text-foreground"
	>
		<p class="flex items-center gap-1.5 font-medium text-warning">
			<TriangleAlert size={13} aria-hidden="true" />
			No authentication
		</p>
		<p class="mt-1 text-muted-foreground">
			Everyone who can reach this page shares one account and can read, change, and delete
			every library here.
		</p>
	</div>
{/if}
