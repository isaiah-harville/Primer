<script lang="ts">
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
	<div class="warning" role="status">
		<strong>Authentication is disabled.</strong>
		Everyone who can reach this page shares one account and can read, change, and delete
		every library here. Do not expose it beyond this machine.
	</div>
{/if}

<style>
	.warning {
		background: #fef3c7;
		border-bottom: 1px solid #d97706;
		color: #78350f;
		font-size: 0.875rem;
		padding: 0.625rem 1rem;
	}
</style>
