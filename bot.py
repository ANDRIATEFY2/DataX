import requests
import subprocess

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_signature(url, user_agent):
    # Appelle le script JS (alverson.js) pour générer la signature
    # Suppose que alverson.js exporte une fonction sign(url, user_agent) qui print la signature
    result = subprocess.run(
        ["node", "-e", f"console.log(require('./alverson.js').sign('{url}', '{user_agent}'))"],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def like_video(url, cookie):
    # Extrait l'ID de la vidéo
    import re
    m = re.search(r'/video/(\d+)', url)
    if not m:
        print("Lien vidéo invalide.")
        return
    video_id = m.group(1)
    api_url = f"https://www.tiktok.com/api/commit/item/digg/?aid=1988&item_id={video_id}"
    signature = get_signature(api_url, USER_AGENT)
    full_url = f"{api_url}&X-Bogus={signature}"
    headers = {
        "user-agent": USER_AGENT,
        "cookie": cookie,
        "referer": url,
        "accept": "application/json, text/plain, */*",
    }
    resp = requests.post(full_url, headers=headers)
    print("Réponse:", resp.text)

def follow_user(url, cookie):
    # Extrait le sec_user_id (ou autre identifiant public) de l'URL
    import re
    m = re.search(r'/@([^/?]+)', url)
    if not m:
        print("Lien profil invalide.")
        return
    username = m.group(1)
    # Il faut récupérer le sec_user_id via l'API publique
    api_url = f"https://www.tiktok.com/@{username}"
    headers = {"user-agent": USER_AGENT, "cookie": cookie}
    resp = requests.get(api_url, headers=headers)
    import re
    m = re.search(r'secUid":"(.*?)"', resp.text)
    if not m:
        print("Impossible de récupérer sec_user_id.")
        return
    sec_user_id = m.group(1)
    # Appel API pour follow
    api_url = f"https://www.tiktok.com/api/follow/user/?aid=1988&sec_user_id={sec_user_id}&type=1"
    signature = get_signature(api_url, USER_AGENT)
    full_url = f"{api_url}&X-Bogus={signature}"
    headers["referer"] = url
    r = requests.post(full_url, headers=headers)
    print("Réponse:", r.text)

def comment_video(url, cookie):
    # Extrait l'ID de la vidéo
    import re
    m = re.search(r'/video/(\d+)', url)
    if not m:
        print("Lien vidéo invalide.")
        return
    video_id = m.group(1)
    comment = input("Entrez le commentaire à poster: ")
    api_url = f"https://www.tiktok.com/api/comment/publish/?aid=1988&item_id={video_id}&text={comment}"
    signature = get_signature(api_url, USER_AGENT)
    full_url = f"{api_url}&X-Bogus={signature}"
    headers = {
        "user-agent": USER_AGENT,
        "cookie": cookie,
        "referer": url,
        "accept": "application/json, text/plain, */*",
    }
    resp = requests.post(full_url, headers=headers)
    print("Réponse:", resp.text)

def main():
    print("Choisis une action:")
    print("1. Liker une vidéo")
    print("2. Follow un compte")
    print("3. Commenter une vidéo")
    choix = input("Tape 1, 2, ou 3: ").strip()
    url = input("Colle l'URL TikTok cible: ").strip()
    cookie = input("Colle ton cookie TikTok: ").strip()
    if choix == "1":
        like_video(url, cookie)
    elif choix == "2":
        follow_user(url, cookie)
    elif choix == "3":
        comment_video(url, cookie)
    else:
        print("Choix invalide.")

if __name__ == "__main__":
    main()
