#!/usr/bin/env python3
"""Apply Eco changes to CodeG0blin Video Live Wallpaper 1.3.0 source.
Run from the upstream checkout. Unique anchors fail closed on substantive source drift.
"""
from pathlib import Path
import argparse
import re

p=argparse.ArgumentParser(); p.add_argument('root',nargs='?',default='.'); p.add_argument('--check',action='store_true'); args=p.parse_args()
root=Path(args.root)
base=root/'app/src/main/java/io/github/codeg0blin/videowallpaper'
changes={}
def read(path): return path.read_text(encoding='utf-8')
def rep(s,old,new):
    count = s.count(old)
    if count == 1:
        return s.replace(old, new, 1)
    # Permit whitespace-only differences between lines, but never ambiguous matches.
    if count == 0 and '\n' in old:
        lines = [line.strip() for line in old.splitlines() if line.strip()]
        pattern = r'(?m)^[ \t]*' + r'[ \t]*\n(?:[ \t]*\n)*[ \t]*'.join(re.escape(line) for line in lines)
        matches = list(re.finditer(pattern, s))
        if len(matches) == 1:
            m = matches[0]
            return s[:m.start()] + new + s[m.end():]
    raise SystemExit(f'Expected one unique match, found {count}: {old[:180]!r}. Use unmodified upstream 1.3.0.')
path=base/'VideoWallpaperService.kt'; s=read(path)
s=rep(s,'import android.content.SharedPreferences','''import android.content.SharedPreferences
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.PowerManager
import android.view.GestureDetector
import android.view.MotionEvent
import androidx.core.content.ContextCompat''')
s=rep(s,'        private var visible = false','''        private var visible = false
        @Volatile private var screenInteractive = false
        @Volatile private var playbackAllowed = false
        @Volatile private var videoWidth = 0
        @Volatile private var videoHeight = 0
        private var prepared = false
        private var posterRequested = false
        private var destroyed = false
        private var powerReceiverRegistered = false
        private var thermalRegistered = false
        private val powerManager by lazy {
            requireNotNull(this@VideoWallpaperService.getSystemService(PowerManager::class.java))
        }
        private val thermalListener = PowerManager.OnThermalStatusChangedListener {
            if (!destroyed) refreshPlayback()
        }
        private val powerReceiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                if (!destroyed) refreshPlayback()
            }
        }
        private val gestures by lazy {
            GestureDetector(this@VideoWallpaperService,
                object : GestureDetector.SimpleOnGestureListener() {
                    override fun onDown(e: MotionEvent): Boolean = true
                    override fun onDoubleTap(e: MotionEvent): Boolean {
                        val settings = prefs ?: return false
                        if (!visible || !screenInteractive || isPreview) return false
                        val paused = settings.getBoolean(PREF_MANUAL_PAUSE, false)
                        settings.edit().putBoolean(PREF_MANUAL_PAUSE, !paused).apply()
                        return true
                    }
                }).apply { setIsLongpressEnabled(false) }
        }

        override fun onTouchEvent(event: MotionEvent) {
            if (!destroyed && !isPreview) gestures.onTouchEvent(event)
            super.onTouchEvent(event)
        }

        private fun refreshPlayback() {
            if (destroyed) return
            screenInteractive = powerManager.isInteractive
            playbackAllowed = visible && screenInteractive && !powerManager.isPowerSaveMode &&
                powerManager.currentThermalStatus < PowerManager.THERMAL_STATUS_SEVERE &&
                (isPreview || prefs?.getBoolean(PREF_MANUAL_PAUSE, false) != true)
            if (!visible || !screenInteractive) stopDrawLoop()
            renderHandler?.post {
                val gif = gifPlayer ?: return@post
                if (playbackAllowed) gif.start() else {
                    gif.pause()
                    if (visible && screenInteractive) gif.showStill()
                }
            }
            val speed = prefs?.getFloat(PREF_PLAYBACK_SPEED, DEFAULT_SPEED) ?: DEFAULT_SPEED
            mediaPlayer?.let { applySpeed(it, speed) }
            if (visible && screenInteractive) startDrawLoopIfVisible()
        }''')
s=rep(s,'            if (!visible) return@Runnable','            if (!visible || !screenInteractive) return@Runnable')
s=rep(s,'''            val player = mediaPlayer
            r.drawFrame(
                holder.surfaceFrame.width(),
                holder.surfaceFrame.height(),
                player?.let { if (weBelieveStarted || it.isPlaying) it.videoWidth else 0 } ?: 0,
                player?.let { if (weBelieveStarted || it.isPlaying) it.videoHeight else 0 } ?: 0
            )''','''            r.drawFrame(
                holder.surfaceFrame.width(), holder.surfaceFrame.height(),
                videoWidth, videoHeight
            )''')
s=rep(s,'            prefs?.registerOnSharedPreferenceChangeListener(this)','''            prefs?.registerOnSharedPreferenceChangeListener(this)
            setTouchEventsEnabled(!isPreview)
            val filter = IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(PowerManager.ACTION_POWER_SAVE_MODE_CHANGED)
            }
            ContextCompat.registerReceiver(this@VideoWallpaperService, powerReceiver,
                filter, ContextCompat.RECEIVER_NOT_EXPORTED)
            powerReceiverRegistered = true
            powerManager.addThermalStatusListener(mainExecutor, thermalListener)
            thermalRegistered = true
            refreshPlayback()''')
s=rep(s,'                        renderHandler?.post(drawFrameRunnable)','''                        if (visible && screenInteractive) {
                            renderHandler?.let { h ->
                                h.removeCallbacks(drawFrameRunnable)
                                h.post(drawFrameRunnable)
                            }
                        }''')
s=rep(s,'''                android.os.Handler(mainLooper).post {
                    preparePlayer(holder)''','''                android.os.Handler(mainLooper).post {
                    if (!destroyed && currentHolder === holder) preparePlayer(holder)''')
start=s.index('        override fun onVisibilityChanged(isVisible: Boolean) {'); end=s.index('        override fun onSurfaceChanged',start)
s=s[:start]+'''        override fun onVisibilityChanged(isVisible: Boolean) {
            super.onVisibilityChanged(isVisible)
            visible = isVisible
            refreshPlayback()
        }
'''+s[end:]
s=rep(s,'''            super.onDestroy()
            prefs?.unregisterOnSharedPreferenceChangeListener(this)''','''            destroyed = true
            playbackAllowed = false
            visible = false
            if (powerReceiverRegistered) {
                this@VideoWallpaperService.unregisterReceiver(powerReceiver)
                powerReceiverRegistered = false
            }
            if (thermalRegistered) {
                powerManager.removeThermalStatusListener(thermalListener)
                thermalRegistered = false
            }
            super.onDestroy()
            prefs?.unregisterOnSharedPreferenceChangeListener(this)''')
s=rep(s,'''            val holder = currentHolder ?: return
            when (key) {''','''            if (key == PREF_MANUAL_PAUSE) {
                refreshPlayback()
                return
            }
            val holder = currentHolder ?: return
            when (key) {''')
s=rep(s,'                            if (gifPlayer != null) drawFrameRunnable.run()','                            if (visible && screenInteractive) drawFrameRunnable.run()')
s=rep(s,'''                player.setOnPreparedListener {
                    consecutiveErrorRetries = 0
                    applySpeed(it, speed)
                    startDrawLoopIfVisible()
                }''','''                player.setOnVideoSizeChangedListener { mp, width, height ->
                    if (mediaPlayer === mp) {
                        videoWidth = width
                        videoHeight = height
                    }
                }
                player.setOnPreparedListener {
                    if (mediaPlayer !== it || destroyed) return@setOnPreparedListener
                    prepared = true
                    videoWidth = it.videoWidth
                    videoHeight = it.videoHeight
                    consecutiveErrorRetries = 0
                    refreshPlayback()
                }''')
s=rep(s,'                if (visible) player.start()','''                if (playbackAllowed) player.start()
                else if (visible && screenInteractive) player.showStill()''')
s=rep(s,'''            if (visible) {
                r.drawGifFrame''','''            if (visible && screenInteractive) {
                r.drawGifFrame''')
start=s.index('        private fun applySpeed(player: MediaPlayer, speed: Float) {'); end=s.index('        /**',start)
s=s[:start]+'''        private fun applySpeed(player: MediaPlayer, speed: Float) {
            if (!prepared || mediaPlayer !== player || destroyed) return
            try {
                if (playbackAllowed) {
                    if (!weBelieveStarted) {
                        player.start()
                        weBelieveStarted = true
                        posterRequested = true
                    }
                    if (speed != appliedSpeed) {
                        player.playbackParams = PlaybackParams().setSpeed(speed)
                        appliedSpeed = speed
                    }
                } else if (weBelieveStarted) {
                    player.pause()
                    weBelieveStarted = false
                } else if (visible && screenInteractive && !posterRequested) {
                    // Ask the decoder for one still frame without starting a loop.
                    // Actual paused-seek rendering depends on the device codec.
                    posterRequested = true
                    player.seekTo(0L, MediaPlayer.SEEK_CLOSEST_SYNC)
                }
            } catch (e: IllegalStateException) {
                Log.w(TAG, "Could not update wallpaper playback", e)
            }
        }
'''+s[end:]
s=rep(s,'            if (!visible) return\n            renderHandler?.post(drawFrameRunnable)','            if (!visible || !screenInteractive) return\n            renderHandler?.post(drawFrameRunnable)')
s=rep(s,'            mediaPlayer = null\n            weBelieveStarted = false','''            mediaPlayer = null
            prepared = false
            posterRequested = false
            videoWidth = 0
            videoHeight = 0
            weBelieveStarted = false''')
s=rep(s,'        const val PREF_VIDEO_URI = "selected_video_uri"','''        const val PREF_MANUAL_PAUSE = "eco_manual_pause"
        const val PREF_VIDEO_URI = "selected_video_uri"''')
changes[path]=s
path=base/'GifPlayer.kt'; s=read(path)
s=rep(s,'    private var running = false','    private var running = false\n    private var hasFrame = false')
s=rep(s,'            if (decoder.frameCount > 1) {','            hasFrame = true\n            if (decoder.frameCount > 1) {')
s=rep(s,'    /** Pauses playback','''    /** Display a first frame without scheduling animation. */
    fun showStill() {
        handler.post {
            if (!running && !hasFrame) {
                decoder.advance()
                hasFrame = onFrame(decoder)
            }
        }
    }
    /** Pauses playback''')
changes[path]=s
path=root/'app/build.gradle.kts'; s=read(path)
s=rep(s,'applicationId = "io.github.codeg0blin.videowallpaper"','applicationId = "io.github.codeg0blin.videowallpaper.eco"')
s=rep(s,'minSdk = 26','minSdk = 29')
s=rep(s,'versionName = "1.3.0"','versionName = "1.3.0-eco.1"')
changes[path]=s
# All anchors must match before writing anything.
for path, content in changes.items():
    if not args.check: path.write_text(content,encoding='utf-8')
    print(('Would modify' if args.check else 'Modified'),path)
