# Code signing in Rialto

**The full guide is [`docs/signing-guide.html`](docs/signing-guide.html).** Open it in a
browser, or click **Read the Guide** inside Rialto's Configure Signing dialog. It is an
offline page: three printable sheets covering the whole Azure setup, what goes wrong, and a
copy-paste prompt for an AI assistant that walks you through the Azure portal step by step.

This file is the short version, for anyone reading the repository on GitHub.

## What it is for

Windows keeps a list of publishers it trusts. Signing puts **your studio's name**
on that list, so the install prompt says who made the game instead of showing a
yellow **"Unknown Publisher"** warning, and antivirus engines stop treating every
new build as a stranger.

One honest note about discs: the big SmartScreen block only fires on files
downloaded from the internet, and a file on a disc cannot carry the marker that
says it was downloaded. On a disc, signing is about the name on the prompt and
about antivirus.

Rialto recommends **Azure Artifact Signing**, Microsoft's own service, about
**$9.99 a month** for 5,000 signatures. It was called **Azure Trusted Signing**
until Microsoft renamed it in January 2026, so older guides use that name.

**Bringing your own account is optional.** Unsigned discs work perfectly.

## What Rialto signs

Two files per build, both with your own account:

1. **`setup.exe`**, your installer.
2. **`menu/menu.exe`**, this disc's own copy of the disc menu.

That second one is deliberate. Rialto is open source, and the `menu.exe` shipped in its
releases is the same generic file on every disc anybody builds. If it arrived pre-signed, some
other studio's name would be on **your** disc and yours would be on strangers'. So the public
copy ships unsigned on purpose, and Rialto signs **your** copy, on **your** disc, with **your**
account. The shared original is never touched.

## Setup, in one screenful

1. Azure account with a pay-as-you-go subscription. A free trial subscription will not work.
2. Register the `Microsoft.CodeSigning` resource provider on that subscription.
3. Create an **Artifact Signing account**, Basic plan. Note the region.
4. **Identity validations → New identity → Public.** Microsoft puts this at 1 to 20 business
   days. Individuals verify in the US and Canada; organisations in a wider list. Start early.
5. Create a **Public Trust** certificate profile once validation completes.
6. Give your own user the **Artifact Signing Certificate Profile Signer** role. Without it
   everything looks correct and signing fails at the last second.
7. Install the [Windows SDK](https://developer.microsoft.com/windows/downloads/windows-sdk/) (for signtool), the [Azure CLI](https://aka.ms/azure-cli) and the
   [.NET 8 runtime](https://dotnet.microsoft.com/download/dotnet/8.0), then run `az login`.
8. In Rialto: **Configure Signing**, pick your region, paste the account name and certificate
   profile name, **Save**, then **Check My Setup** until it says **You are ready to sign.**
9. Tick **Sign Final Build** and build.

The endpoint must match the region your account and certificate profile live in. A mismatch is
the usual cause of a 403 at signing time. Picking the region in Rialto fills the endpoint in
for you.

## If you are not signing

Leave it unconfigured. Builds still work, and **Sign Final Build** simply pauses after the
installer is created so you can sign with anything else, then carries on to the ISO.

Free alternative for open-source projects: **SignPath Foundation**, though the publisher line
reads SignPath Foundation rather than your name. The comparison table in the HTML guide covers
the rest.

## Bring your own account, always

Rialto is a tool, not a signing service. Everyone signs with their own Microsoft account and
their own name. Nothing you sign leaves your PC: only a fingerprint of the file goes to
Microsoft, and the signature comes back.
