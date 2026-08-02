# Desgrabador de YouTube

Aplicación Flask que obtiene los subtítulos disponibles (manuales o automáticos)
de un video de YouTube y los muestra como transcripción. El frontend se sirve
desde Flask y consulta el backend mediante la ruta relativa `/get_subs`, por lo
que funciona tanto en local como en el dominio público.

## Cómo funciona

- `GET /` entrega la interfaz web.
- `GET /get_subs?url=<URL_DE_YOUTUBE>` ejecuta `yt-dlp` para obtener únicamente
  subtítulos en formato VTT, los transforma y devuelve JSON.
- El modo de varios videos del navegador hace una solicitud a `/get_subs` por
  cada URL, en orden.

No se descarga ni se convierte el video o el audio. Por ello, FFmpeg no es una
dependencia de esta aplicación. Cada solicitud usa archivos temporales aislados
que se eliminan al terminar.

## Desarrollo local

Se requiere Python 3.12 o superior:

```powershell
python -m pip install -r requirements.txt
python youtubesubs_app.py
```

Abrí `http://127.0.0.1:5000`.

## Despliegue gratuito en Render

El proyecto incluye `render.yaml` para crear un Web Service gratuito:

- Instalación: `pip install -r requirements.txt`
- Inicio: Gunicorn escucha el puerto que Render entrega en `PORT`.
- Despliegue automático: cada push a la rama configurada (recomendado `main`).

### Primera publicación

1. Creá un repositorio vacío en GitHub, sin añadir README, `.gitignore` ni
   licencia desde GitHub.
2. En esta carpeta inicializá Git y publicalo (reemplazá la URL):

   ```powershell
   git init
   git add .
   git commit -m "Preparar despliegue en Render"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
   git push -u origin main
   ```

3. Iniciá sesión en [Render](https://render.com), elegí **New > Blueprint**,
   conectá GitHub y seleccioná el repositorio. Render detectará `render.yaml`.
4. Confirmá el plan **Free** y creá el servicio. Al finalizar, Render mostrará
   una URL HTTPS con formato `https://desgrabador-youtube.onrender.com`.

No hay secretos que configurar ni se debe subir ninguna contraseña o token al
repositorio.

### Actualizaciones

```powershell
git add .
git commit -m "Descripción del cambio"
git push origin main
```

Render construirá y publicará automáticamente la nueva versión. Consultá los
logs del servicio en Render si un despliegue falla.

## Límites del plan gratuito

Render detiene el servicio después de 15 minutos sin tráfico. La primera visita
posterior puede tardar aproximadamente un minuto mientras vuelve a iniciar. Hay
750 horas de instancia gratuitas por espacio de trabajo y límites mensuales de
ancho de banda y minutos de compilación. El disco es efímero, lo cual no afecta
esta aplicación porque los subtítulos son temporales.
