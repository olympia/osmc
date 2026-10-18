# olympia/osmc fork: host-side cleanup for the mediacenter-osmc build.
#
# build.sh rewrites files/DEBIAN/control and files-debug/DEBIAN/control in place
# and leaves the toolchain chroot mounts (/proc, /root/.ccache, /mnt) behind.
# This file is sourced by build.sh, which runs on the host and then again inside
# the toolchain chroot. Only the host side does anything here: it saves the two
# control files and, on every exit of the script, restores them and unmounts the
# chroot.
#
# Chroot detection follows build_in_env in ../common.sh: ischroot returning 0 or
# 2 is treated as being inside the chroot.

ischroot
olympia_chrootval=$?
if [ $olympia_chrootval -ne 0 ] && [ $olympia_chrootval -ne 2 ]
then
	# All targets of this build.sh (rbp2, rbp4, vero3, vero5) use the armv7 toolchain
	OLYMPIA_TCDIR="/opt/osmc-tc/armv7-toolchain-osmc"
	OLYMPIA_PKGDIR="$(pwd)"
	OLYMPIA_BACKUP="$(mktemp -d)"
	cp -p "${OLYMPIA_PKGDIR}/files/DEBIAN/control" "${OLYMPIA_BACKUP}/control"
	cp -p "${OLYMPIA_PKGDIR}/files-debug/DEBIAN/control" "${OLYMPIA_BACKUP}/control-debug"

	function olympia_host_cleanup()
	{
		echo -e "Restoring control files and unmounting the toolchain chroot"
		if [ -f "${OLYMPIA_BACKUP}/control" ]; then cp -p "${OLYMPIA_BACKUP}/control" "${OLYMPIA_PKGDIR}/files/DEBIAN/control"; fi
		if [ -f "${OLYMPIA_BACKUP}/control-debug" ]; then cp -p "${OLYMPIA_BACKUP}/control-debug" "${OLYMPIA_PKGDIR}/files-debug/DEBIAN/control"; fi
		rm -rf "${OLYMPIA_BACKUP}"
		# /proc can be mounted more than once on top of itself
		while mountpoint -q "${OLYMPIA_TCDIR}/proc"; do umount "${OLYMPIA_TCDIR}/proc" || break; done
		if mountpoint -q "${OLYMPIA_TCDIR}/root/.ccache"; then umount "${OLYMPIA_TCDIR}/root/.ccache"; fi
		if mountpoint -q "${OLYMPIA_TCDIR}/mnt"; then umount "${OLYMPIA_TCDIR}/mnt"; fi
	}
	trap olympia_host_cleanup EXIT
fi
