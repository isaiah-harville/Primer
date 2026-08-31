<script lang="ts">
	import { Alert } from '@sivir-ui/svelte';

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
-->
{#if !authEnabled}
	<Alert.Root variant="warning" class="rounded-none border-x-0 border-t-0">
		<Alert.Title>Authentication is disabled</Alert.Title>
		<Alert.Description>
			Everyone who can reach this page shares one account and can read, change, and delete
			every library here. Do not expose it beyond this machine.
		</Alert.Description>
	</Alert.Root>
{/if}
