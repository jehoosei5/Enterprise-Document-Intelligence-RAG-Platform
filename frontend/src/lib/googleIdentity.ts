// Minimal surface of the Google Identity Services (GIS) client we use.
// The GIS script (loaded via <script> in index.html) attaches this to
// window.google; no official/complete type package is used here since we
// only touch a couple of methods.
interface GoogleNotification {
  isNotDisplayed: () => boolean
  isSkippedMoment: () => boolean
}

interface GoogleAccountsId {
  initialize(config: { client_id: string; callback: (response: { credential: string }) => void }): void
  prompt(momentListener?: (notification: GoogleNotification) => void): void
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsId } }
  }
}

let initialized = false

/** Triggers Google's One Tap / sign-in prompt, resolving with the ID
 * token on success. Rejects if the GIS script hasn't loaded or the user
 * closes the prompt without completing sign-in.
 */
export function promptGoogleSignIn(): Promise<string> {
  return new Promise((resolve, reject) => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
    if (!clientId) {
      reject(new Error('VITE_GOOGLE_CLIENT_ID is not configured'))
      return
    }
    if (!window.google) {
      reject(new Error('Google sign-in script has not loaded yet — try again in a moment'))
      return
    }

    if (!initialized) {
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => resolve(response.credential),
      })
      initialized = true
    }

    window.google.accounts.id.prompt((notification) => {
      if (notification.isNotDisplayed?.() || notification.isSkippedMoment?.()) {
        reject(new Error('Google sign-in was dismissed or unavailable'))
      }
    })
  })
}
