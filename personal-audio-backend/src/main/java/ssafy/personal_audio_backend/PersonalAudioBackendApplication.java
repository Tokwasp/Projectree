package ssafy.personal_audio_backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@EnableJpaAuditing
@SpringBootApplication
public class PersonalAudioBackendApplication {

	public static void main(String[] args) {
		SpringApplication.run(PersonalAudioBackendApplication.class, args);
	}

}
