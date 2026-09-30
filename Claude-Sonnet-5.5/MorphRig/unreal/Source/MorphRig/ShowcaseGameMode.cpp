#include "ShowcaseGameMode.h"
#include "OperativeCharacter.h"
#include "ShowcasePlayerController.h"
#include "ShowcaseHUD.h"

AShowcaseGameMode::AShowcaseGameMode()
{
	DefaultPawnClass = AOperativeCharacter::StaticClass();
	PlayerControllerClass = AShowcasePlayerController::StaticClass();
	HUDClass = AShowcaseHUD::StaticClass();
}
