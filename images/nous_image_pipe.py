# -*- coding: utf-8 -*-
"""
title: Gerador de Imagem Local
author: Guilherme (Nous)
version: 0.2.0
required_open_webui_version: 0.5.0
license: MIT
description: >
  Um "modelo" do Open WebUI que detecta automaticamente quando o usuario quer
  GERAR UMA IMAGEM e roteia para o ComfyUI (Flux). Para qualquer outra coisa,
  encaminha ao Ollama (gemma4:12b). 100% assincrono (nao trava o servidor) e
  entrega a imagem como ARQUIVO nativo do Open WebUI (aparece inline no chat).

Arquitetura:
  Chat -> (este Pipe) -> intencao de imagem? -> ComfyUI/Flux -> arquivo -> inline
                       \-> senao -------------> Ollama/gemma4:12b -> texto
"""
import re
import os
import json
import time
import uuid
import base64
import asyncio
import urllib.parse
from typing import Optional

import aiohttp
from pydantic import BaseModel, Field

# Mesmo num_ctx do chat (monitor/register_model_ctx.py): com outro valor o
# Ollama recarrega o modelo (no 0.30 o padrao chega a 256k e estoura a VRAM).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))


# --------------------------------------------------------------------------
# Workflow embutido (Flux Schnell, formato API do ComfyUI).
# --------------------------------------------------------------------------
FLUX_SCHNELL_WORKFLOW = {
    "10": {"class_type": "UnetLoaderGGUF",
           "inputs": {"unet_name": "flux1-schnell-Q4_K_S.gguf"},
           "_meta": {"title": "UNET (GGUF)"}},
    "11": {"class_type": "DualCLIPLoader",
           "inputs": {"clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                      "clip_name2": "clip_l.safetensors", "type": "flux"},
           "_meta": {"title": "CLIP"}},
    "12": {"class_type": "VAELoader",
           "inputs": {"vae_name": "ae.safetensors"},
           "_meta": {"title": "VAE"}},
    "6": {"class_type": "CLIPTextEncode",
          "inputs": {"text": "", "clip": ["11", 0]},
          "_meta": {"title": "Positive Prompt"}},
    "7": {"class_type": "CLIPTextEncode",
          "inputs": {"text": "", "clip": ["11", 0]},
          "_meta": {"title": "Negative Prompt"}},
    "5": {"class_type": "EmptySD3LatentImage",
          "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
          "_meta": {"title": "Latent"}},
    "3": {"class_type": "KSampler",
          "inputs": {"seed": 0, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
                     "scheduler": "simple", "denoise": 1.0, "model": ["10", 0],
                     "positive": ["6", 0], "negative": ["7", 0],
                     "latent_image": ["5", 0]},
          "_meta": {"title": "Sampler"}},
    "8": {"class_type": "VAEDecode",
          "inputs": {"samples": ["3", 0], "vae": ["12", 0]},
          "_meta": {"title": "Decode"}},
    "9": {"class_type": "SaveImage",
          "inputs": {"filename_prefix": "nous", "images": ["8", 0]},
          "_meta": {"title": "Save"}},
}

# Gatilhos de intencao de imagem (PT + EN).
_VERBS = (r"cri[ae]|gere|gera|gerar|desenh[ae]|fa[cç]a|fazer|ilustr[ae]|pinte|"
          r"produz[ae]|render(?:ize)?|imagin[ae]|mostr[ae]|quero|preciso|"
          r"create|generate|draw|make|paint|render|show|give\s+me|want")
_NOUNS = (r"imagem|imagens|logo|logotipo|[ií]cone|foto|retrato|paisagem|wallpaper|"
          r"arte|ilustra[cç][aã]o|desenho|cena|p[oô]ster|poster|capa|avatar|"
          r"pintura|quadro|banner|mascote|personagem|figurinha|"
          r"image|picture|portrait|landscape|illustration|drawing|art|icon|photo|"
          r"painting|poster|banner|mascot|character|sticker")
# Verbo + substantivo na mesma sentença
_INTENT_RE = re.compile(rf"\b(?:{_VERBS})\b[^.?!\n]{{0,60}}\b(?:{_NOUNS})\b", re.IGNORECASE)
# Verbos que so' fazem sentido para imagem: "desenhe um farol" nao precisa de
# substantivo. No comeco da frase (opcionalmente apos "por favor"/"pode"/"quero que voce").
_STRONG_RE = re.compile(
    r"^\s*(?:(?:por\s+favor|pode|poderia|consegue|quero\s+que\s+voc[eê]|please|can\s+you|could\s+you)[\s,]+)*"
    r"(?:desenh(?:[ae]|ar)|pint(?:e|ar)|ilustr(?:e|ar)|imagin(?:e|ar)|draw|paint|illustrate)\b", re.IGNORECASE)
# Prefixo /img, /imagine etc.
_PREFIX_RE = re.compile(r"^\s*(?:/(?:img|image|imagem)\b|imagine\b)", re.IGNORECASE)
# "uma foto de X", "uma imagem de X" sem verbo explícito
_NOUN_LEAD_RE = re.compile(rf"\b(?:uma?|the|an?)\s+(?:{_NOUNS})\b", re.IGNORECASE)


def _last_user_text(messages):
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content", "")
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c
                             if isinstance(p, dict) and p.get("type") == "text")
            return (c or "").strip()
    return ""


def _split_content(content):
    """De um content estilo OpenAI -> (texto, [imagens_base64_sem_prefixo])."""
    if isinstance(content, str):
        return content, []
    texts, imgs = [], []
    for p in content or []:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            texts.append(p.get("text", ""))
        elif p.get("type") == "image_url":
            url = (p.get("image_url") or {}).get("url", "")
            if isinstance(url, str) and url.startswith("data:") and "," in url:
                imgs.append(url.split(",", 1)[1])
    return " ".join(t for t in texts if t).strip(), imgs


def _ollama_messages(messages):
    """Converte mensagens (formato OpenAI) -> formato Ollama, PRESERVANDO as
    imagens em base64 (campo 'images'). E' isto que habilita a VISAO do Gemma."""
    out = []
    for m in messages or []:
        text, imgs = _split_content(m.get("content", ""))
        for im in (m.get("images") or []):
            if isinstance(im, str):
                imgs.append(im.split(",", 1)[1]
                            if im.startswith("data:") and "," in im else im)
        msg = {"role": m.get("role", "user"), "content": text}
        if imgs:
            msg["images"] = imgs
        out.append(msg)
    return out


def _last_user_has_image(messages):
    """True se a ULTIMA mensagem do usuario traz uma imagem anexada."""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            _, imgs = _split_content(m.get("content", ""))
            return bool(imgs or m.get("images"))
    return False


def _clean_image_prompt(text):
    return _PREFIX_RE.sub("", text).strip(" :,-").strip() or text


class Pipe:
    class Valves(BaseModel):
        COMFYUI_URL: str = Field(default="http://localhost:8188")
        OLLAMA_URL: str = Field(default="http://localhost:11434")
        TEXT_MODEL: str = Field(default="gemma4:12b")
        WORKFLOW_PATH: str = Field(default="")
        UNET_GGUF: str = Field(default="flux1-schnell-Q4_K_S.gguf")
        T5_NAME: str = Field(default="t5xxl_fp8_e4m3fn.safetensors")
        CLIP_L_NAME: str = Field(default="clip_l.safetensors")
        VAE_NAME: str = Field(default="ae.safetensors")
        WIDTH: int = Field(default=1024)
        HEIGHT: int = Field(default=1024)
        STEPS: int = Field(default=4)
        IMAGE_TIMEOUT: int = Field(default=300)
        USE_LLM_CLASSIFIER: bool = Field(default=False)
        # Tempo que o Gemma fica na VRAM apos a ultima mensagem (libera rapido).
        KEEP_ALIVE: str = Field(default="30s")
        # Flux + T5 ocupam ~11 GB. Se sobrar menos que isto na placa, o modelo
        # de linguagem e' descarregado antes de gerar (senao a geracao vaza
        # para a RAM e leva o dobro do tempo). 0 desliga a conferencia.
        NEEDED_VRAM_GB: float = Field(default=12.0)
        # Depois da imagem, o ComfyUI solta a VRAM (o chat volta a ter espaco).
        FREE_VRAM_AFTER: bool = Field(default=True)

    def __init__(self):
        self.type = "manifold"
        self.valves = self.Valves()

    def pipes(self):
        return [{"id": "nous", "name": "Gerador de Imagem Local"}]

    # ----------------------------------------------------------- roteador (async)
    async def pipe(self, body: dict, __user__: Optional[dict] = None,
                   __request__=None, __metadata__: Optional[dict] = None,
                   __event_emitter__=None):
        messages = body.get("messages", [])
        user_text = _last_user_text(messages)
        # Imagem ANEXADA pelo usuario => pergunta de VISAO (nao gerar nova imagem).
        if (not _last_user_has_image(messages)
                and user_text and self._is_image_request(user_text)):
            async for chunk in self._image_flow(
                _clean_image_prompt(user_text), __request__, __user__,
                __metadata__, __event_emitter__):
                yield chunk
            return
        # Passa ao Ollama sem tools (evita que o Gemma retorne JSON de tool-call)
        async for chunk in self._text_flow(body, messages):
            yield chunk

    # ----------------------------------------------------------- deteccao
    def _is_image_request(self, text: str) -> bool:
        return bool(_PREFIX_RE.search(text) or _STRONG_RE.search(text)
                    or _INTENT_RE.search(text) or _NOUN_LEAD_RE.search(text))

    # ----------------------------------------------------------- imagem (ComfyUI)
    def _load_workflow(self):
        path = self.valves.WORKFLOW_PATH or ""
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return json.loads(json.dumps(FLUX_SCHNELL_WORKFLOW))

    def _apply_params(self, graph, prompt):
        v = self.valves
        for node in graph.values():
            ct = node.get("class_type")
            meta = node.get("_meta", {})
            ins = node.get("inputs", {})
            if meta.get("title") == "Positive Prompt":
                ins["text"] = prompt
            elif ct == "KSampler":
                ins["seed"] = uuid.uuid4().int % (2 ** 32)
                ins["steps"] = v.STEPS
            elif ct in ("EmptySD3LatentImage", "EmptyLatentImage"):
                ins["width"] = v.WIDTH
                ins["height"] = v.HEIGHT
            elif ct == "UnetLoaderGGUF":
                ins["unet_name"] = v.UNET_GGUF
            elif ct == "DualCLIPLoader":
                ins["clip_name1"] = v.T5_NAME
                ins["clip_name2"] = v.CLIP_L_NAME
            elif ct == "VAELoader":
                ins["vae_name"] = v.VAE_NAME

    @staticmethod
    def _first_image(info):
        for out in (info.get("outputs") or {}).values():
            for img in out.get("images", []) or []:
                return {"filename": img.get("filename"),
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output")}
        return None

    async def _ensure_comfyui(self) -> bool:
        """Pede ao Nous Monitor para subir o ComfyUI se necessário.
        O monitor (porta 8990) tem permissão para lançar processos — o pipe não."""
        # Verifica primeiro diretamente (evita round-trip ao monitor se já está no ar)
        base = self.valves.COMFYUI_URL.rstrip("/")
        chk = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=chk) as s:
                async with s.get(f"{base}/system_stats") as r:
                    if r.status < 500:
                        return True
        except Exception:
            pass

        # Delega a inicialização ao monitor (aguarda até 90 s lá dentro)
        mon = aiohttp.ClientTimeout(total=100)
        try:
            async with aiohttp.ClientSession(timeout=mon) as s:
                async with s.post("http://127.0.0.1:8990/comfyui/start") as r:
                    data = await r.json()
                    return bool(data.get("ok"))
        except Exception:
            return False

    async def _make_room(self):
        """Descarrega os modelos do Ollama se a VRAM livre nao comporta o Flux.
        So' mexe no Ollama quando falta espaco de verdade."""
        need = float(self.valves.NEEDED_VRAM_GB or 0) * 1024 ** 3
        if need <= 0:
            return
        base = self.valves.COMFYUI_URL.rstrip("/")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                async with s.get(f"{base}/system_stats") as r:
                    dev = (await r.json())["devices"][0]
                free = (dev.get("vram_free") or 0) + (dev.get("torch_vram_free") or 0)
                if free >= need:
                    return
                ollama = self.valves.OLLAMA_URL.rstrip("/")
                async with s.get(f"{ollama}/api/ps") as r:
                    loaded = [m.get("name") or m.get("model")
                              for m in (await r.json()).get("models", [])]
                for name in filter(None, loaded):
                    async with s.post(f"{ollama}/api/generate",
                                      json={"model": name, "keep_alive": 0}) as r:
                        await r.read()
                await asyncio.sleep(2)  # o Windows leva um instante para devolver a VRAM
        except Exception:
            pass  # sem Ollama/ComfyUI legivel: segue e deixa a geracao decidir

    async def _free_comfy(self):
        """Pede ao ComfyUI para soltar os modelos da VRAM (o processo continua no ar)."""
        base = self.valves.COMFYUI_URL.rstrip("/")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
                async with s.post(f"{base}/free",
                                  json={"unload_models": True, "free_memory": True}) as r:
                    await r.read()
        except Exception:
            pass

    async def _comfy_generate(self, prompt) -> Optional[bytes]:
        base = self.valves.COMFYUI_URL.rstrip("/")
        graph = self._load_workflow()
        self._apply_params(graph, prompt)
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            # Retry no /prompt: o ComfyUI pode aceitar /system_stats mas ainda
            # não estar pronto para enfileirar prompts logo após subir.
            pid = None
            for attempt in range(10):
                try:
                    async with s.post(f"{base}/prompt",
                                      json={"prompt": graph, "client_id": uuid.uuid4().hex}) as r:
                        r.raise_for_status()
                        pid = (await r.json())["prompt_id"]
                    break
                except Exception:
                    if attempt == 9:
                        raise
                    await asyncio.sleep(3)
            if pid is None:
                raise RuntimeError("ComfyUI não aceitou o prompt após várias tentativas")
            deadline = time.time() + self.valves.IMAGE_TIMEOUT
            ref = None
            while time.time() < deadline:
                async with s.get(f"{base}/history/{pid}") as r:
                    hist = await r.json()
                if pid in hist:
                    ref = self._first_image(hist[pid])
                    if ref:
                        break
                    st = hist[pid].get("status", {})
                    if st.get("status_str") == "error":
                        raise RuntimeError("erro no workflow do ComfyUI")
                await asyncio.sleep(1.0)
            if not ref:
                return None
            q = urllib.parse.urlencode(ref)
            async with s.get(f"{base}/view?{q}") as r:
                r.raise_for_status()
                return await r.read()

    async def _save_image(self, data, request, user, metadata):
        """Salva como arquivo nativo do Open WebUI -> URL servida e persistente.
        Cai para data URI (base64) se algo no caminho nativo mudar de versao."""
        try:
            from open_webui.routers.images import upload_image
            from open_webui.models.users import Users
            uobj = await Users.get_user_by_id(user["id"]) if user and user.get("id") else None
            meta = {}
            if metadata:
                meta = {"chat_id": metadata.get("chat_id"),
                        "message_id": metadata.get("message_id")}
            _, url = await upload_image(request, data, "image/png", meta, uobj)
            # 0.9.x devolve o endereco; 0.10+ devolve {"id", "url", "name", ...}
            if isinstance(url, dict):
                url = url.get("url") or ""
            if not url:
                raise ValueError("upload_image sem endereco")
            return url
        except Exception:
            return "data:image/png;base64," + base64.b64encode(data).decode()

    async def _emit(self, emit, description, done):
        if emit:
            try:
                await emit({"type": "status",
                            "data": {"description": description, "done": done}})
            except Exception:
                pass

    async def _image_flow(self, prompt, request, user, metadata, emit):
        await self._emit(emit, "🎨 Verificando ComfyUI…", False)
        ok = await self._ensure_comfyui()
        if not ok:
            await self._emit(emit, "ComfyUI offline", True)
            yield f"*(O ComfyUI não está acessível em {self.valves.COMFYUI_URL} e não foi possível iniciá-lo automaticamente. Verifique a instalação.)*"
            return
        await self._make_room()
        await self._emit(emit, "🎨 Gerando imagem com Flux…", False)
        try:
            data = await self._comfy_generate(prompt)
        except Exception as e:
            await self._emit(emit, "Falha na geração", True)
            yield f"*(Falha ao gerar imagem via ComfyUI em {self.valves.COMFYUI_URL}: {e})*"
            return
        finally:
            if self.valves.FREE_VRAM_AFTER:
                await self._free_comfy()
        if not data:
            await self._emit(emit, "Sem imagem", True)
            yield "*(O ComfyUI não retornou a imagem dentro do tempo limite.)*"
            return
        url = await self._save_image(data, request, user, metadata)
        await self._emit(emit, "Imagem pronta", True)
        aviso = "\n\n*⚠️ Imagem feita por IA, sem filtros: confira antes de usar. Você é responsável pelo conteúdo gerado.*"
        yield f"![{prompt}]({url}){aviso}"

    # ----------------------------------------------------------- texto (Ollama)
    async def _text_flow(self, body, messages):
        payload = {"model": self.valves.TEXT_MODEL,
                   "messages": _ollama_messages(messages), "stream": True,
                   "keep_alive": self.valves.KEEP_ALIVE,
                   "tools": []}  # garante que o Gemma não use tool-calling
        payload["options"] = {"num_ctx": NUM_CTX}
        if body.get("temperature") is not None:
            payload["options"]["temperature"] = body["temperature"]
        timeout = aiohttp.ClientTimeout(total=900)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.post(f"{self.valves.OLLAMA_URL}/api/chat", json=payload) as r:
                    r.raise_for_status()
                    async for raw in r.content:
                        if not raw:
                            continue
                        try:
                            data = json.loads(raw.decode("utf-8"))
                        except json.JSONDecodeError:
                            continue
                        chunk = (data.get("message") or {}).get("content", "")
                        if chunk:
                            yield chunk
                        if data.get("done"):
                            break
        except Exception as e:
            yield f"\n\n*(Erro ao falar com o Ollama em {self.valves.OLLAMA_URL}: {e})*"
